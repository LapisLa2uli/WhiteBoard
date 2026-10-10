const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c=vm.createContext({window:{},document:{hidden:false},location:{hash:''},console,setTimeout,clearTimeout,Date});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/boot\(\);/,''),c);
(async()=>{
  vm.runInContext(`state={has_snapshot:true};route='/home';render=()=>{};api=async()=>({auth_required:true});`,c);
  await vm.runInContext('checkSchoolSession()',c);
  assert.equal(vm.runInContext('route',c),'/login');
  assert.equal(vm.runInContext('needsLogin()',c),true);
  assert.equal(c.location.hash,'/login');
  vm.runInContext(`state={has_snapshot:true};route='/home';api=async()=>{throw Error('Network unavailable')};`,c);
  await vm.runInContext('checkSchoolSession()',c);
  assert.equal(vm.runInContext('route',c),'/home');
  vm.runInContext(`api=async()=>{pollGen++;return {auth_required:true}}`,c);
  await vm.runInContext('checkSchoolSession()',c);
  assert.equal(vm.runInContext('route',c),'/home');
  vm.runInContext(`state.offline=true;api=async()=>{throw Error('Offline must not check')}`,c);
  await vm.runInContext('checkSchoolSession()',c);
  assert.equal(vm.runInContext('route',c),'/home');
  vm.runInContext(`
    jobError='Your Blackboard session expired';
    api=async()=>({has_snapshot:true,job:{error:''},assignments:[]});
  `,c);
  await vm.runInContext('loadState()',c);
  assert.equal(vm.runInContext('jobError',c),'');
  vm.runInContext(`jobError='Old error';beginLoading('login','Signing in')`,c);
  assert.equal(vm.runInContext('jobError',c),'');
  vm.runInContext(`
    loading=null;state={has_snapshot:true,marker:'new'};
    api=async()=>{pollGen++;return {has_snapshot:true,marker:'old',job:{error:'Old error'}}};
  `,c);
  await vm.runInContext('loadState()',c);
  assert.equal(vm.runInContext('state.marker',c),'new');
  assert.equal(vm.runInContext('jobError',c),'');
  console.log('Session UI: expiry routing, network failures, offline mode and stale responses passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
