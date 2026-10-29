/* Shared explicit desktop actions. Availability and grants are managed in native Settings. */
(()=>{
  async function perform(name,args,options={}) {
    const result=await window.NeuraChat.executeManual(name,args,options);
    if(options.chat){setHas(true);bubble('n','Neura [إجراء]','#81C784','shield',result.message);}
    return result;
  }
  window.NeuraSkills={perform,handleChat:q=>window.NeuraChat.handleChat(q)};
})();
