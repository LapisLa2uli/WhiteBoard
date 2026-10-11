const fs=require('fs'),vm=require('vm'),assert=require('assert');
const app={innerHTML:''};
const c=vm.createContext({
  window:{}, document:{body:{style:{}},getElementById:id=>id==='app'?app:null},
  location:{hash:''},console,setTimeout,clearTimeout,Date,
});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/boot\(\);/,''),c);
// Exercise the actual render path with and without a saved dashboard.
for(const saved of [false,true]){
  for(const expired of [false,true]){
    for(const kind of ['login','interactive']){
      vm.runInContext(`state={has_snapshot:${saved},auth_required:${expired}};route='/login';loading=null;render()`,c);
      assert(app.innerHTML.includes('id="login-form"'));
      vm.runInContext(`beginLoading('${kind}','Signing in…')`,c);
      assert(app.innerHTML.includes('class="load-track"'));
      assert(app.innerHTML.includes('2%'));
      assert(app.innerHTML.includes('id="cancel-loading"'));
      assert(!app.innerHTML.includes('id="login-form"'));
      vm.runInContext(`loading.percent=.4;loading.message='Checking course content';render()`,c);
      assert(app.innerHTML.includes('40%'));
      assert(app.innerHTML.includes('Checking course content'));
      // Failed/cancelled sign-in returns to the form with its message.
      vm.runInContext(`loading=null;jobError='Sign-in cancelled';render()`,c);
      assert(app.innerHTML.includes('id="login-form"'));
      assert(app.innerHTML.includes('Sign-in cancelled'));
    }
  }
}
// A published dashboard stage must replace full-screen progress while indexing continues.
vm.runInContext(`
shellFrame=()=>'<div id="shell">Dashboard</div>';
paintChrome=()=>{chromeLoading=!!loading};
paintFilterChrome=paintCourses=paintFilterDialog=paintPage=tickCountdowns=()=>{};
state={has_snapshot:true,auth_required:false};route='/home';
loading={kind:'login',percent:.4,message:'Indexing files'};render();
`,c);
assert(app.innerHTML.includes('id="shell"'));
assert(!app.innerHTML.includes('class="load-track"'));
assert.equal(vm.runInContext('chromeLoading',c),true);
// Ordinary refresh keeps the usable dashboard visible.
vm.runInContext(`beginLoading('refresh','Refreshing')`,c);
assert(app.innerHTML.includes('id="shell"'));
assert(!app.innerHTML.includes('class="load-track"'));
console.log('Login progress: saved/empty/expired sessions, SSO, progress updates, cancellation and dashboard transition passed.');
