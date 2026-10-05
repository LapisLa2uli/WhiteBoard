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
