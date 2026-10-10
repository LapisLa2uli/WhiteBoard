const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('static/app.js', 'utf8').replace(/boot\(\);/, '');
const c = vm.createContext({window:{},document:{},location:{hash:''},console,setTimeout,clearTimeout,setInterval,Date});
vm.runInContext(source, c);
vm.runInContext(`
state={assignments:[{id:'a',title:'Alpha',course:'Course',course_id:'c',status:'todo',base_status:'todo'},{id:'b',title:'Beta',course:'Course',course_id:'c',status:'todo',base_status:'todo'}],calendar:[{id:'d',assignment_id:'a',status:'todo',finished:false}],home_due:[{id:'d',assignment_id:'a'}],course_pages:{}};
inActiveFilter=()=>true;
query.assignments='Alpha';
applyAssignmentUpdates([{id:'a',status:'submitted',manual:true,ignored:false}]);
assignmentItems('all');
applyAssignmentUpdates([{id:'a',status:'todo',manual:false,ignored:false}]);
`, c);
assert.equal(vm.runInContext('todoCount()',c),2);
assert.equal(vm.runInContext('state.calendar[0].status',c),'todo');
assert.equal(vm.runInContext('state.calendar[0].manual',c),false);
vm.runInContext(`applyAssignmentUpdates([{id:'a',status:'todo',manual:false,ignored:true}]); applyAssignmentUpdates([{id:'a',status:'todo',manual:false,ignored:false}]);`,c);
assert.equal(vm.runInContext('state.home_due.length',c),1);
assert.equal(vm.runInContext('state.home_due[0].ignored',c),false);
console.log('UI regression: badge, mark/undo, ignore/restore passed.');
vm.runInContext(`
state.content_nodes=[{id:'folder',name:'Week 1',course_id:'c',kind:'folder'},{id:'file',name:'Notes.pdf',course_id:'c',parent_id:'folder',kind:'file'}];
contentIndex=null;
`,c);
assert.equal(vm.runInContext('folderTrail(state.content_nodes, state.content_nodes[1])',c),'Week 1');
assert.equal(vm.runInContext('ensureContentIndex().trails.size',c),1);
vm.runInContext(`state.content_nodes=[{id:'folder',name:'Week 2',course_id:'c',kind:'folder'},{id:'file',name:'Notes.pdf',course_id:'c',parent_id:'folder',kind:'file'}]`,c);
assert.equal(vm.runInContext('folderTrail(state.content_nodes, state.content_nodes[1])',c),'Week 2');
console.log('UI regression: folder path cache invalidates with content revisions.');

vm.runInContext(`
sizeNode={id:'size-file',name:'Example.pdf',course_id:'c',kind:'file',extension:'pdf',size_label:'3.2 MB',size_title:'3,328,388 bytes',date:'Today',url:'https://school.example/file'};
`,c);
for (const expression of ['fileRow(sizeNode,0)', 'explorerRow(nodeToItem(sizeNode),"course:c",true,false)']) {
  const html=vm.runInContext(expression,c);
  assert(html.includes('3.2 MB'));
  assert(html.includes('title="3,328,388 bytes"'));
}
vm.runInContext(`sizeNode.size_label='0 B';sizeNode.size_title='0 bytes'`,c);
assert(vm.runInContext('fileRow(sizeNode,0)',c).includes('0 B'));
console.log('UI regression: file sizes and exact-byte tooltips render in Contents.');

vm.runInContext(`sizeNode.kind='assignment';sizeNode.type_label='Assignment link';`,c);
assert(vm.runInContext('fileRow(sizeNode,0)',c).includes('aria-label="Assignment link"'));
assert(vm.runInContext('fileRow(sizeNode,0)',c).includes('content-type-label'));
vm.runInContext(`state.content_nodes=[sizeNode];contentsSelected=new Set([sizeNode.id]);contentsFolders.clear();`,c);
assert.equal(vm.runInContext('hasDownloadSelection()',c),false);
console.log('UI regression: assignment links have distinct icons and cannot download as files.');

vm.runInContext(`pendingEvent={id:'pending',title:'Review',kind:'other',classification_pending:true,course_id:'c',fill:'#fff',ink:'#000'};`,c);
assert(vm.runInContext('eventChip(pendingEvent,false)',c).includes('Checking type'));
assert(vm.runInContext('assignCard(pendingEvent,false)',c).includes('Checking type'));
console.log('UI regression: unresolved calendar classification is disclosed during loading.');

vm.runInContext(`
state.home_due=[
  {id:'work',title:'Essay',kind:'assignment',course_id:'c'},
  {id:'test',title:'Quiz',kind:'test',course_id:'c'},
  {id:'meeting',title:'Office hours',kind:'other',course_id:'c'},
  pendingEvent,
  {id:'hidden',title:'Excluded course',kind:'other',course_id:'hidden'},
  {id:'done',title:'Finished work',kind:'assignment',finished:true},
  {id:'ignored',title:'Ignored work',kind:'assignment',ignored:true}
];
inActiveFilter=(id)=>id!=='hidden';
`,c);
let home=vm.runInContext('homeView()',c);
const section=(html,id)=>html.match(new RegExp('<section aria-labelledby="'+id+'">([\\s\\S]*?)</section>'))[1];
assert(section(home,'home-assignments').includes('Essay'));
assert(section(home,'home-assignments').includes('Quiz'));
assert(!section(home,'home-assignments').includes('Office hours'));
assert(section(home,'home-events').includes('Office hours'));
assert(!section(home,'home-events').includes('Essay'));
assert(!section(home,'home-events').includes('Review'));
assert(section(home,'home-checking').includes('Review'));
assert(!section(home,'home-checking').includes('data-assign-mark'));
for (const title of ['Excluded course','Finished work','Ignored work']) assert(!home.includes(title));
vm.runInContext('state.home_due=[]',c);
home=vm.runInContext('homeView()',c);
assert(home.includes('No assignments this week.'));
assert(home.includes('No events this week.'));
assert(!home.includes('home-checking'));
console.log('UI regression: dashboard separates coursework, events, and unresolved entries with filters intact.');

vm.runInContext(`
state.home_due=[
 {id:'past',title:'Past meeting',kind:'other',ts:1},
 {id:'future',title:'Future meeting',kind:'other',ts:Date.now()/1000+100},
 {id:'overdue',title:'Overdue essay',kind:'assignment',ts:1},
 {...pendingEvent,ts:1}
];
`,c);
home=vm.runInContext('homeView()',c);
assert(!home.includes('Past meeting'));
assert(home.includes('Future meeting')&&home.includes('Overdue essay')&&home.includes('Review'));
vm.runInContext(`
route='/home';
clock=1000; Date.now=()=>clock*1000;
eventNode={dataset:{homeEventAt:1001},removed:false,remove(){this.removed=true}};
emptyNode={hidden:true};
document.querySelectorAll=(selector)=>selector==='[data-home-event-at]'&&!eventNode.removed?[eventNode]:[];
document.getElementById=()=>emptyNode;
tickCountdowns();
`,c);
assert.equal(vm.runInContext('eventNode.removed',c),false);
vm.runInContext('clock=1001;tickCountdowns()',c);
assert.equal(vm.runInContext('eventNode.removed',c),true);
assert.equal(vm.runInContext('emptyNode.hidden',c),false);
assert.equal(vm.runInContext('state.home_due.length',c),4);
console.log('UI regression: events disappear at their planned time without deleting calendar data or overdue assignments.');
