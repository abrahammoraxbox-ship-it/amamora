(() => {
  const clientId = document.body.dataset.googleClientId;
  const target = document.getElementById("google-button");
  if (!clientId || !target) return;
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const start = () => {
    if (!window.google?.accounts?.id) return setTimeout(start, 100);
    google.accounts.id.initialize({client_id:clientId, callback:async ({credential}) => {
      target.classList.add("is-loading");
      try {
        const response=await fetch("/acceso/google",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify({credential})});
        const data=await response.json();
        if (!response.ok) throw new Error(data.error||"No pudimos ingresar con Google.");
        location.assign(data.redirect);
      } catch(error) {
        target.classList.remove("is-loading");
        const message=document.createElement("p");message.className="form-error";message.textContent=error.message;target.after(message);
      }
    }});
    google.accounts.id.renderButton(target,{theme:"outline",size:"large",shape:"rectangular",text:"continue_with",locale:"es",width:340});
  };
  start();
})();
