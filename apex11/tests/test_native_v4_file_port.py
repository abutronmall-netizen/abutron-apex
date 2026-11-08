"""Mock filesystem-only atomic V4 port tests. No installed MT5 EA / orders."""
from dataclasses import replace
from pathlib import Path
import os
import pytest

from abutron_replacement.native_v4_file_port import (
    NativeV4FilePort, V4_REQUEST_NAME, V3_REQUEST_NAME,
    V4_CAPABILITY_PREFIX, V4_CAPABILITY_MAGIC, V4_PROTOCOL,
)
from abutron_replacement.production_contracts import FeedRefused
from test_exclusive_native_writer import assemble, call, OWNER, CID


def ready(tmp_path):
    x=assemble(tmp_path)
    result=call(x)
    assert result.request_queued
    request=x["port"].requests[0]
    e=x["supervisor"].evidence
    files=tmp_path/"MQL5"/"Files"
    folder=files/"ABUTRON"
    receipt=folder/"receipts"
    receipt.mkdir(parents=True)
    cap=files/(V4_CAPABILITY_PREFIX+request.worker_nonce+".txt")
    cap.write_text("\n".join([
        V4_CAPABILITY_MAGIC,request.worker_nonce,request.mt5_login,
        "Deriv-Demo","DEMO",str(request.activation_revision),
        str(int(x["now"].timestamp())),"0.10",
        "OFF_REVISION_CHECK_AT_CONSUME","LIVE_FORBIDDEN",
    ])+"\n")
    port=NativeV4FilePort(account_id=CID,account_login=request.mt5_login,
        files_dir=files,worker_uid=os.getuid(),clock=lambda:x["now"].timestamp())
    return x,port,request,e,cap,folder


def test_v4_request_file_written_atomically_without_v3_fallback(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    port.assert_ready(req,e)
    port.queue_once(req,e)
    request_file=folder/V4_REQUEST_NAME
    assert request_file.is_file()
    assert request_file.stat().st_uid==os.getuid()
    assert request_file.stat().st_mode & 0o077 == 0
    assert not (folder/V3_REQUEST_NAME).exists()
    raw=request_file.read_bytes()
    assert raw.count(b"\r\n")==13
    assert b"\n" not in raw.replace(b"\r\n", b"")
    lines=request_file.read_text().splitlines()
    assert len(lines)==13
    assert lines==[
        V4_PROTOCOL,req.worker_nonce,req.signal_id,req.mt5_login,
        "Deriv-Demo",req.symbol,req.side,req.volume_lots,
        req.stop_price,req.take_price,str(req.activation_revision),
        str(req.expires_at_utc),"SEND_DEMO_ONLY"]
    with pytest.raises(FeedRefused,match="ALREADY_PENDING"):
        port.queue_once(req,e)
    assert request_file.read_text().splitlines()==lines


def test_no_v4_native_capability_blocks_filesystem_write(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    cap.unlink()
    with pytest.raises(FileNotFoundError):
        port.assert_ready(req,e)
    assert not (folder/V4_REQUEST_NAME).exists()


def test_stale_or_unfenced_capability_rejected(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    lines=cap.read_text().splitlines()
    lines[6]=str(int(x["now"].timestamp())-40)
    cap.write_text("\n".join(lines)+"\n")
    with pytest.raises(FeedRefused,match="CAPABILITY_STALE"):
        port.assert_ready(req,e)
    lines[6]=str(int(x["now"].timestamp()))
    lines[8]="NO_CLIENT_REVISION_FENCE"
    cap.write_text("\n".join(lines)+"\n")
    with pytest.raises(FeedRefused,match="REVISION_FENCE_CAPABILITY"):
        port.assert_ready(req,e)
    assert not (folder/V4_REQUEST_NAME).exists()


def test_v3_request_or_existing_native_receipt_blocks(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    (folder/V3_REQUEST_NAME).write_text("LEGACY_PENDING")
    with pytest.raises(FeedRefused,match="ALREADY_PENDING"):
        port.assert_ready(req,e)
    (folder/V3_REQUEST_NAME).unlink()
    (folder/"receipts"/(req.signal_id+".txt")).write_text("PREEXISTING")
    with pytest.raises(FeedRefused,match="RECEIPT_ALREADY_EXISTS"):
        port.assert_ready(req,e)


def test_symlinked_capability_and_folder_refused(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    cap.rename(cap.with_suffix(".saved"))
    cap.symlink_to(cap.with_suffix(".saved"))
    with pytest.raises(FeedRefused,match="SYMLINK"):
        port.assert_ready(req,e)
    cap.unlink()
    cap.with_suffix(".saved").rename(cap)
    folder.rename(tmp_path/"other")
    folder.symlink_to(tmp_path/"other",target_is_directory=True)
    with pytest.raises(FeedRefused,match="FOLDER_UNSAFE"):
        port.assert_ready(req,e)


def test_wrong_account_revision_side_stop_geometry_refused(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    with pytest.raises(FeedRefused,match="ACCOUNT_OR_NONCE"):
        port.assert_ready(replace(req,account_id="a"*32),e)
    with pytest.raises(FeedRefused,match="REVISION_FENCED"):
        port.assert_ready(replace(req,activation_revision=req.activation_revision+1),e)
    with pytest.raises(FeedRefused,match="BUY_SL_TP"):
        port.assert_ready(replace(req,stop_price="9999999"),e)
    with pytest.raises(FeedRefused,match="PRICE_OR_VOLUME"):
        port.assert_ready(replace(req,volume_lots="NaN"),e)
    assert not (folder/V4_REQUEST_NAME).exists()


def test_v3_broker_ea_proof_cannot_make_v4_order(tmp_path):
    x,port,req,e,cap,folder=ready(tmp_path)
    e=replace(e,native_ea_protocol=3,revision_fenced_by_native_ea=False)
    with pytest.raises(FeedRefused,match="REVISION_FENCED"):
        port.assert_ready(req,e)
    assert not (folder/V4_REQUEST_NAME).exists()
