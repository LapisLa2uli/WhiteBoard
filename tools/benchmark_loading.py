"""Compare loading strategies using deterministic, non-private representative data."""
import json
import statistics
import sys
import tempfile
import time
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['WHITEBOARD_DATA_DIR'] = directory
        import data
        data.install()
        import present
        import blackboard.api as api
        from blackboard.models import Snapshot, Course, Assignment, Deadline, Grade, ContentNode
        from blackboard.store import Store
        now = datetime.now(timezone.utc)
        s = Snapshot(user_id='benchmark', fetched_at=now)
        s.courses = [Course(id=f'c{i}', name=f'Course {i}') for i in range(40)]
        s.assignments = [Assignment(id=f'a{i}',course_id=f'c{i%40}',title=f'Assignment number {i}',due_at=now+timedelta(days=i%30)) for i in range(119)]
        s.grades = [Grade(id=f'g{i}',course_id=f'c{i%40}',title=f'Assignment number {i}',score='7',points_earned=7,points_possible=10) for i in range(136)]
        s.deadlines = [Deadline(id=f'd{i}',assignment_id=f'a{i%119}',course_id=f'c{i%40}',title=f'Assignment number {i%119}',when=now+timedelta(days=i%30),kind='assignment') for i in range(699)]
        s.content_nodes = [ContentNode(id=f'n{i}',course_id=f'c{i%40}',title=f'File {i}.pdf') for i in range(2906)]
        store = Store(); store.snapshot=s; store.save_cache()
        results = {}
        def measure(name, fn):
            times=[]
            for _ in range(3):
                start=time.perf_counter(); result=fn(); times.append(time.perf_counter()-start)
            results[name]={'median_seconds':round(statistics.median(times),4),'json_bytes':len(json.dumps(result).encode())}
            return result
        cached = api._norm_title
        with patch.object(api,'_norm_title',cached.__wrapped__):
            baseline=measure('uncached_full',lambda:present.build_state(s))
        optimized=measure('title_cache_full',lambda:present.build_state(s))
        # Countdown labels can cross a second boundary; compare substantive records.
        def stable(value):
            if isinstance(value, dict):
                return {k: stable(v) for k,v in value.items() if k not in {'countdown'}}
            if isinstance(value, list): return [stable(v) for v in value]
            return value
        baseline, optimized = stable(baseline), stable(optimized)
        assert baseline == optimized, 'Title caching changed presentation data'
        measure('lean_dashboard',lambda:present.build_state(s,include_content=False,course_id=''))
        present.build_state(include_content=False,course_id='')
        measure('warm_dashboard',lambda:present.build_state(include_content=False,course_id=''))
        print(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
