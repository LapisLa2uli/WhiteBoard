const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c=vm.createContext({window:{},document:{getElementById:()=>null},location:{hash:''},console,setTimeout,clearTimeout,Date});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/boot\(\);/,''),c);
vm.runInContext(`
paintPage=()=>{};showToast=()=>{};
calls=[];
notice={ok:true,browser_notice:true,browser:'chrome',school:'https://school.example',username:'student"<test>',title:'Essay <draft>'};
api=async(path,body)=>{calls.push({path,body});return notice};
`,c);
(async()=>{
  await vm.runInContext(`openUrl('https://school.example/work','Essay','assignment')`,c);
  let html=vm.runInContext('browserOpenModal()',c);
  assert(html.includes('Open Blackboard sign-in'));
  assert(html.includes('id="browser-open-page"'));
  assert(!html.match(/id="browser-notice-snooze"[^>]*checked/));
  vm.runInContext(`onChange({target:{id:'browser-notice-snooze',checked:true}})`,c);
  assert(html.includes('student&quot;&lt;test&gt;'));
  assert(!html.includes('Essay <draft>'));
  assert(!html.includes('type="password"'));
  assert.equal(vm.runInContext('calls[0].body.browser_action',c),undefined);
  vm.runInContext(`api=async(path,body)=>{calls.push({path,body});return {ok:true,message:'Return here after signing in'}}`,c);
  await vm.runInContext(`continueBrowserOpen('signin')`,c);
  assert(vm.runInContext('browserOpenModal()',c).includes('Return here after signing in'));
  assert.equal(vm.runInContext('calls.at(-1).body.browser',c),'chrome');
  assert.equal(vm.runInContext('calls.at(-1).body.browser_action',c),'signin');
  assert.equal(vm.runInContext('calls.at(-1).body.snooze_notice',c),false);
  assert(vm.runInContext('browserOpenModal()',c).match(/id="browser-notice-snooze"[^>]*checked/));
  assert.equal(vm.runInContext('calls.at(-1).body.url',c),'https://school.example/work');
  assert(!vm.runInContext('browserOpenModal()',c).includes(' disabled'));
  // Launch failures keep the request available for retry.
  vm.runInContext(`api=async()=>({ok:false,message:'Browser unavailable'})`,c);
  await vm.runInContext(`continueBrowserOpen('page')`,c);
  assert(vm.runInContext('browserOpenModal()',c).includes('Browser unavailable'));
  vm.runInContext(`api=async(path,body)=>{calls.push({path,body});return {ok:true}}`,c);
  await vm.runInContext(`continueBrowserOpen('page')`,c);
  assert.equal(vm.runInContext('browserOpenDialog',c),null);
  assert.equal(vm.runInContext('calls.at(-1).body.id',c),'assignment');
  assert.equal(vm.runInContext('calls.at(-1).body.browser_action',c),'page');
  assert.equal(vm.runInContext('calls.at(-1).body.snooze_notice',c),true);
  // Cancel never opens the requested page.
  vm.runInContext(`browserOpenDialog={...notice,request:{url:'work'}}; beforeCancel=calls.length;
    onClick({target:{closest:selector=>selector==='#browser-open-cancel'?{}:null}});`,c);
  assert.equal(vm.runInContext('browserOpenDialog',c),null);
  assert.equal(vm.runInContext('calls.length===beforeCancel',c),true);
  // A delayed response after sign-out must not restore the dialog.
  vm.runInContext(`api=async()=>{pollGen++;return notice}`,c);
  await vm.runInContext(`openUrl('https://school.example/work')`,c);
  assert.equal(vm.runInContext('browserOpenDialog',c),null);
  console.log('Browser notice: saved username, sign-in/open sequence, retry, cancel and stale responses passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
