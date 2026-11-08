"""Non-mutating, evidence-based FP Markets broker-clock diagnosis.

Never labels stale quotes as a healthy timezone offset, never fabricates ticks,
and never relaxes production feed freshness. Native trading remains disabled.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from statistics import median
from datetime import datetime, timezone
import math
from .production_contracts import FeedRefused


@dataclass(frozen=True)
class FPClockDiagnosis:
    status:str
    candidate_offset_seconds:int|None
    quote_count:int
    fresh_quote_count:int
    median_age_seconds:float|None
    likely_weekend_closed:bool


def diagnose_fp_clock(*, emitted_epoch:int, broker_quote_epochs:list[int],
                      observed_utc:int|None=None, required_fresh:int=5,
                      allow_offsets:tuple[int,...]=tuple(3600*i for i in range(-14,15)))->FPClockDiagnosis:
    """Test plausible *whole-hour* server clock offsets using a fresh cohort.

    A raw quote 24h behind the export isn't a '-24h time zone': it's stale.
    Clock diagnostic is independent of actual broker feed authorization.
    """
    now=int(datetime.now(timezone.utc).timestamp()) if observed_utc is None else int(observed_utc)
    if not isinstance(emitted_epoch,int) or abs(now-emitted_epoch)>240:
        raise FeedRefused('FP_NATIVE_EXPORT_TIME_UNVERIFIED')
    if not isinstance(broker_quote_epochs,list) or len(broker_quote_epochs)<required_fresh or required_fresh<5:
        raise FeedRefused('FP_QUOTE_COHORT_INSUFFICIENT')
    if any(not isinstance(q,int) or isinstance(q,bool) for q in broker_quote_epochs):
        raise FeedRefused('FP_QUOTE_TIMESTAMP_INVALID')
    # A broker clock offset is only knowable when >=5 independent fresh quotes
    # agree with one candidate within [-300,+30] seconds.
    outcomes=[]
    for offset in allow_offsets:
        if offset % 3600 or abs(offset)>14*3600:
            raise FeedRefused('FP_UNSAFE_OFFSET_CANDIDATE')
        ages=[emitted_epoch-(q-offset) for q in broker_quote_epochs]
        fresh=[age for age in ages if -30<=age<=300]
        if len(fresh)>=required_fresh and len(fresh)*2>len(ages) and not any(age< -30 for age in ages):
            outcomes.append((len(fresh),-abs(median(fresh)),offset,ages))
    dt=datetime.fromtimestamp(now,timezone.utc)
    weekend=dt.weekday()>=5
    if not outcomes:
        # How recent would the quotes be under their *best* plausible clock?
        best_age=min((median([emitted_epoch-(q-offset) for q in broker_quote_epochs])
                      for offset in allow_offsets),default=math.inf)
        if best_age>300:
            return FPClockDiagnosis('STALE_NATIVE_QUOTES_NOT_A_TIMEZONE_ERROR',None,
                len(broker_quote_epochs),0,round(float(best_age),1),weekend)
        return FPClockDiagnosis('BROKER_CLOCK_OFFSET_UNVERIFIED',None,
            len(broker_quote_epochs),0,None,weekend)
    outcomes.sort(reverse=True)
    top=outcomes[0]
    if len(outcomes)>1 and outcomes[1][0]==top[0] and outcomes[1][1]==top[1]:
        return FPClockDiagnosis('AMBIGUOUS_CLOCK_OFFSET',None,
            len(broker_quote_epochs),top[0],None,weekend)
    _,_,offset,ages=top
    return FPClockDiagnosis('FRESH_COHORT_CLOCK_OFFSET_VERIFIED',offset,
        len(broker_quote_epochs),top[0],round(float(median(ages)),1),weekend,
        )


def read_native_quote_epoch_fields(lines:list[str])->tuple[int,list[int]]:
    """Only parse emitted epoch and MT5 tick timestamps; account binding done upstream."""
    if not isinstance(lines,list) or len(lines)<14 or lines[0]!='ABUTRON_FP_QUOTES_V1':
        raise FeedRefused('FP_QUOTE_NATIVE_SCHEMA_INVALID')
    try:
        emitted=int(lines[6]); rows=[line.split('\t') for line in lines[7:-1]]
        epochs=[int(x[2]) for x in rows if len(x)==5]
    except (ValueError,IndexError,TypeError):
        raise FeedRefused('FP_NATIVE_QUOTE_TIME_UNREADABLE') from None
    if not lines[-1].startswith('END\t') or len(epochs)<5:
        raise FeedRefused('FP_NATIVE_QUOTE_END_MARKER_INVALID')
    return emitted,epochs
