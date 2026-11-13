(()=>{"use strict";
const kind=document.body.dataset.flow;
const action=document.getElementById("actionForm");
const request=document.getElementById("requestForm");
const result=document.getElementById("result");
const params=new URLSearchParams(location.hash.replace(/^#/,""));
const token=params.get("token")||"";
if(location.hash){history.replaceState(null,"",location.pathname);}
action.hidden=!token;request.hidden=!!token;
function notice(m,err){result.hidden=false;result.textContent=m;result.style.color=err?"#f5a4a4":"#d7ad4d";}
async function post(path,body){
 const r=await fetch("/account/api/account/"+path,{method:"POST",credentials:"same-origin",
   headers:{"Content-Type":"application/json"},body:JSON.stringify(body),cache:"no-store"});
 const d=await r.json().catch(()=>({error:"Unexpected response"}));
 if(!r.ok)throw new Error(d.error||"Request failed");
 return d;
}
request.addEventListener("submit",async e=>{
 e.preventDefault();const btn=request.querySelector("button");btn.disabled=true;
 try{await post(kind==="verify"?"resend":"password/request",{email:document.getElementById("email").value.trim()});
     notice("If the account is eligible, a secure email will arrive shortly.");request.reset();}
 catch(err){notice(err.message,true);}finally{btn.disabled=false;}
});
action.addEventListener("submit",async e=>{
 e.preventDefault();const btn=action.querySelector("button");btn.disabled=true;
 try{
  if(kind==="verify"){await post("verify",{token});notice("Email verified. Your ABUTRON account is active. You can sign in.");}
  else{const p=document.getElementById("password").value;
       if(p!==document.getElementById("confirm").value)throw new Error("Passwords do not match");
       await post("password/confirm",{token,password:p});
       document.getElementById("password").value="";document.getElementById("confirm").value="";
       notice("Password updated. Sign in to ABUTRON using your new password.");}
  action.hidden=true;
 }catch(err){notice(err.message,true);}
 finally{btn.disabled=false;}
});
})();