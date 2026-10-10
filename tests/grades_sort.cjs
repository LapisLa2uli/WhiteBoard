const fs=require('fs'),vm=require('vm'),assert=require('assert');
const c=vm.createContext({window:{},document:{},location:{hash:''},console,setTimeout,clearTimeout,Date});
vm.runInContext(fs.readFileSync('static/app.js','utf8').replace(/boot\(\);/,''),c);
vm.runInContext(`
state={courses:[],graded:[
{id:'z',title:'Zulu',course:'Alpha',course_id:'a',deadline_ts:20},
{id:'a',title:'Alpha',course:'Zulu',course_id:'z',deadline_ts:10},
{id:'u',title:'Undated',course:'Beta',course_id:'b',deadline_ts:0}
],pending:[]};
state.pending=state.graded.map(g=>({...g,id:'pending-'+g.id}));
inActiveFilter=(id)=>id!=='hidden';
shownCourses=()=>[];
`,c);
for(const [sort,expected] of [
 ['name-asc','a,u,z'],['name-desc','z,u,a'],
 ['course-asc','z,u,a'],['course-desc','a,u,z'],
 ['deadline-desc','z,a,u'],['deadline-asc','a,z,u']
]){
 vm.runInContext(`gradesSort=${JSON.stringify(sort)}`,c);
 assert.equal(vm.runInContext('sortGrades(state.graded).map(g=>g.id).join(",")',c),expected);
 assert.equal(vm.runInContext('state.graded.map(g=>g.id).join(",")',c),'z,a,u');
 const html=vm.runInContext('gradesLists()',c);
 const titles={a:'Alpha',u:'Undated',z:'Zulu'};
 for (const key of ['graded','pending']) {
   const group=html.split('data-folder="'+key+'"')[1].split('</section>')[0];
   const rendered=[...group.matchAll(/<strong>(Alpha|Undated|Zulu)<\/strong>/g)].map(match=>match[1]);
   assert.deepEqual(rendered,expected.split(',').map(id=>titles[id]));
 }
 assert(vm.runInContext('gradesView()',c).includes('value="'+sort+'" selected'));
}
vm.runInContext(`state.graded.push({id:'h',title:'Hidden',course_id:'hidden'});query.grades='Alpha';`,c);
let html=vm.runInContext('gradesLists()',c);
assert(!html.includes('Undated')&&!html.includes('Hidden'));
assert(html.includes('Alpha')&&html.includes('Zulu'));
vm.runInContext(`
query.grades=''; pageSize=1; pages.graded=2;pages.pending=2;
route='/grades'; listRoot={innerHTML:''}; document.getElementById=()=>listRoot;
onChange({target:{id:'grades-sort',value:'deadline-desc'}});
`,c);
assert.equal(vm.runInContext('pages.graded',c),0);
assert.equal(vm.runInContext('pages.pending',c),0);
html=vm.runInContext('listRoot.innerHTML',c);
assert(html.includes('Zulu</strong>')&&!html.includes('Undated</strong>'));
assert(html.includes('1–1 of 3'));
assert(vm.runInContext('gradeCard({course_id:"a",title:"Essay",due:"Posted 8 Oct",deadline:"Due 1 Oct"})',c).includes('Due 1 Oct'));
console.log('Grades regression: six sort orders, missing deadlines, filters, pagination, and date labels passed.');
