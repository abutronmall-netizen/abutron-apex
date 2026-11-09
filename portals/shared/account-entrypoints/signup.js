(()=>{
"use strict";
const form=document.getElementById("register");
const choices=[...form.querySelectorAll('input[name="consent"]')];
const adult=document.getElementById("adult");
const submit=document.getElementById("submit");
const message=document.getElementById("message");
const count=document.getElementById("count");
const progress=document.getElementById("bar");
const password=document.getElementById("password");
const confirm=document.getElementById("confirm");
const fields=["name","email","country","password","confirm"].map(id=>document.getElementById(id));
const helpPassword=document.getElementById("passwordHelp");
const helpConfirm=document.getElementById("confirmHelp");
let submitting=false;
function updateConsent(){
 const accepted=choices.filter(c=>c.checked).length;
 count.textContent=accepted+" of 9 accepted";
 progress.style.width=(100*accepted/9)+"%";
 submit.disabled=submitting||accepted!==9||!adult.checked;
}
function clearError(){
 message.hidden=true;
 message.textContent="";
}
function displayError(reason, field){
 message.textContent=reason;
 message.hidden=false;
 if(field){
   field.setAttribute("aria-invalid","true");
   field.focus({preventScroll:true});
   field.scrollIntoView({behavior:"smooth",block:"center"});
 }else{
   message.scrollIntoView({behavior:"smooth",block:"center"});
 }
}
function passwordFeedback(){
 const n=password.value.length;
 const sufficient=n>=12 && n<=128;
 if(helpPassword){
   helpPassword.textContent=!n?"At least 12 characters required.":sufficient?
     "Password length accepted.":"Password too short: "+n+" of 12 characters.";
   helpPassword.classList.toggle("invalid",n>0&&!sufficient);
   helpPassword.classList.toggle("valid",sufficient);
 }
 const hasConfirmation=confirm.value.length>0;
 if(helpConfirm){
   helpConfirm.textContent=!hasConfirmation?"Re-enter the same password.":confirm.value!==password.value?
     "Passwords do not match.":"Passwords match.";
   helpConfirm.classList.toggle("invalid",hasConfirmation&&confirm.value!==password.value);
   helpConfirm.classList.toggle("valid",hasConfirmation&&confirm.value===password.value);
 }
}
function validate(){
 const fullName=document.getElementById("name");
 const email=document.getElementById("email");
 const country=document.getElementById("country");
 if(!fullName.value.trim())return ["Enter your full legal name.",fullName];
 if(fullName.value.trim().length<2)return ["Your legal name must contain at least 2 characters.",fullName];
 if(!fullName.checkValidity())return ["Check your full legal name (maximum 120 characters).",fullName];
 if(!email.value.trim())return ["Enter your email address.",email];
 if(!email.checkValidity())return ["Enter a valid email address, such as name@example.com.",email];
 if(!country.value)return ["Select your country of residence.",country];
 if(password.value.length<12)return ["Password is too short. Enter at least 12 characters.",password];
 if(password.value.length>128)return ["Password is too long. Use no more than 128 characters.",password];
 if(!confirm.value)return ["Re-enter your password in the confirmation field.",confirm];
 if(confirm.value!==password.value)return ["The two passwords do not match. Re-enter the same password.",confirm];
 if(choices.some(box=>!box.checked))return ["Read and acknowledge all nine mandatory documents.",null];
 if(!adult.checked)return ["Confirm that you are at least 18 years old.",adult];
 return null;
}
for(const box of choices){
 // Preserve previous acknowledgement choices for a failed submission.
 try{box.checked=sessionStorage.getItem("apex_doc_"+box.value)==="1";}catch{}
 box.addEventListener("change",()=>{
   try{if(box.checked)sessionStorage.setItem("apex_doc_"+box.value,"1");
       else sessionStorage.removeItem("apex_doc_"+box.value);}catch{}
   updateConsent();
 });
}
adult.addEventListener("change",updateConsent);
for(const field of fields){
 field.addEventListener("input",()=>{
   field.removeAttribute("aria-invalid");
   if(field===password||field===confirm)passwordFeedback();
   if(!message.hidden&&validate()===null)clearError();
 });
 field.addEventListener("change",()=>field.removeAttribute("aria-invalid"));
}
passwordFeedback();updateConsent();
form.addEventListener("submit",async(event)=>{
 event.preventDefault();
 if(submitting)return;
 clearError();
 const problem=validate();
 if(problem){displayError(...problem);return;}
 // The server validates all fields and document receipt hashes independently.
 const data=new FormData(form);
 const payload={
   name:String(data.get("name")||"").trim(),
   email:String(data.get("email")||"").trim(),
   country:data.get("country"),
   password:password.value,
   adult:true,
   consents:Object.fromEntries(choices.map(c=>[c.value,c.checked]))
 };
 // Avoid collecting passwords in diagnostic logs or browser storage.
 submitting=true;submit.textContent="Submitting securely…";updateConsent();
 try{
   const response=await fetch("/account/api/register",{
     method:"POST",
     headers:{"Content-Type":"application/json"},
     body:JSON.stringify(payload),
     credentials:"same-origin",
     cache:"no-store"
   });
   const result=await response.json().catch(()=>({error:"Unexpected registration response."}));
   if(!response.ok)throw new Error(result.error||"Registration unavailable. Please try again.");
   password.value="";confirm.value="";
   form.hidden=true;
   document.getElementById("success").hidden=false;
   try{choices.forEach(c=>sessionStorage.removeItem("apex_doc_"+c.value));}catch{}
   document.getElementById("success").scrollIntoView({behavior:"smooth",block:"start"});
 }catch(error){
   displayError(error instanceof Error?error.message:"Registration failed. Please try again.",null);
 }finally{
   submitting=false;submit.textContent="Create account →";updateConsent();
 }
});
})();