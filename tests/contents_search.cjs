const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c=vm.createContext({window:{},document:{},location:{hash:''},console,setTimeout,clearTimeout,Date});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/boot\(\);/,''),c);
vm.runInContext(`
state={courses:[{id:'a',name:'Alpha course'},{id:'z',name:'Zulu course'}],content_nodes:[
{id:'f',name:'Unit 1',course_id:'a',kind:'folder'},
{id:'1',name:'Notes A.pdf',course_id:'a',parent_id:'f',kind:'file',extension:'pdf',date_ts:20,date:'20 Jan',size_label:'2 KB'},
{id:'2',name:'Notes Z.pdf',course_id:'z',kind:'file',extension:'pdf',date_ts:10,date:'10 Jan',size_label:'1 KB'}]};
shownCourses=()=>state.courses;
`,c);
assert.equal(vm.runInContext('contentsSearchControls()',c),'');
assert(!vm.runInContext('contentsView()',c).includes('id="contents-search-here"'));
assert(vm.runInContext('contentsView()',c).includes('aria-label="Clear search"'));
vm.runInContext(`query.contents='Notes';`,c);
assert(vm.runInContext('contentsSearchControls()',c).includes('Only this folder'));
let html=vm.runInContext('contentsSearchView(state.courses,state.content_nodes,query.contents)',c);
assert(html.includes('Notes A.pdf')&&html.includes('Notes Z.pdf'));
assert(html.includes('data-sort="course"')&&html.includes('data-sort="date"'));
vm.runInContext(`contentsCourseMode='include';contentsCourseIds=new Set(['a']);`,c);
html=vm.runInContext('contentsSearchView(state.courses,state.content_nodes,query.contents)',c);
assert(html.includes('Notes A.pdf')&&!html.includes('Notes Z.pdf'));
vm.runInContext(`contentsCourseMode='exclude';`,c);
html=vm.runInContext('contentsSearchView(state.courses,state.content_nodes,query.contents)',c);
assert(!html.includes('Notes A.pdf')&&html.includes('Notes Z.pdf'));
vm.runInContext(`contentsCourseMode='include';contentsCourseIds.clear();`,c);
assert(vm.runInContext('contentsSearchView(state.courses,state.content_nodes,query.contents)',c).includes('No contents match'));
vm.runInContext(`contentsCourseMode='all';contentsSearchHere=true;contentsPath=['course:a','f'];`,c);
html=vm.runInContext('contentsSearchView(state.courses,state.content_nodes,query.contents)',c);
assert(html.includes('Notes A.pdf')&&!html.includes('Notes Z.pdf'));
vm.runInContext(`hits=[{name:'Z',course:'Alpha',kind:'file',node:{date_ts:20}},{name:'A',course:'Zulu',kind:'file',node:{date_ts:10}}];`,c);
for(const [key,dir,expected] of [['course',1,'Z'],['course',-1,'A'],['date',1,'A'],['date',-1,'Z']]){
 vm.runInContext(`contentsSort={key:${JSON.stringify(key)},dir:${dir}}`,c);
 assert.equal(vm.runInContext('sortSearchHits(hits)[0].name',c),expected);
}
vm.runInContext(`
input={value:'Notes',focus:()=>{input.focused=true;}};
document.getElementById=id=>id==='contents-search'?input:null;
paintContentsRoot=()=>{};
clearContentsSearch();
`,c);
assert.equal(vm.runInContext('query.contents',c),'');
assert.equal(vm.runInContext('contentsSearchHere',c),false);
assert.equal(vm.runInContext('contentsPath[1]',c),'f');
assert.equal(vm.runInContext('input.focused',c),true);
console.log('Contents search: conditional controls, clear, include/exclude, folder scope and course/date ordering passed.');
