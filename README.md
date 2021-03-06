The HERA Librarian
==================

This system keeps track of all of the primary data products stored at a given
site. There is a Flask-based server that keeps track of everything using a
database and presents a nice frontend, and Python client code that can make
various requests of one or more servers.

All of the server code is in a subdirectory called `server`. See
[the README there](server/README.md) for information on how to run a server.

Besides the server, this repository provides a Python module,
`hera_librarian`, that lets you talk to one *or more* Librarians
programmatically. Documentation not yet available. Install it with

```
python setup.py install
```

in this directory. This also provides a few scripts:

* `add_obs_librarian.py` — Meant to be run on a store computer; notifies a
  Librarian of new files that it ought to be aware of.
* `librarian_launch_copy.py` — Instruct one Librarian server to start copying
  a file to another Librarian.
* `upload_to_librarian.py` — Uploads a file to a Librarian. If the origin
  file is already known to a different Librarian, `librarian_launch_copy.py`
  should be used to preserve metadata.
