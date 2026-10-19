"""Encode Docker --mount fields as CSV, independently of shell quoting."""
import csv
import io

def mount(source, destination, readonly=True):
    text = io.StringIO(newline='')
    csv.writer(text, lineterminator='\n').writerow(
        ['type=bind', 'src=' + str(source), 'dst=' + str(destination),
         *(['readonly'] if readonly else [])])
    return ['--mount', text.getvalue()[:-1]]
