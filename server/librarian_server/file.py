# -*- mode: python; coding: utf-8 -*-
# Copyright 2016 the HERA Collaboration
# Licensed under the BSD License.

"Files."

from __future__ import absolute_import, division, print_function, unicode_literals

__all__ = str('''
File
FileInstance
FileEvent
''').split ()

import datetime, json, re
from flask import flash, redirect, render_template, url_for

from . import app, db
from .dbutil import NotNull
from .webutil import ServerError, json_api, login_required, optional_arg, required_arg
from .observation import Observation
from .store import Store


class File (db.Model):
    """A File describes a data product generated by HERA.

    The information described in a File structure never changes, and is
    universal between Librarians. Actual "instances" of files come and go, but
    a File record should never be deleted. The only exception to this is the
    "source" column, which is Librarian-dependent.

    A File may represent an actual flat file or a directory tree. The latter
    use case is important for MIRIAD data files, which are directories, and
    which we want to store in their native form for rapid analysis.

    File names are unique. Here, the "name" is a Unix 'basename', i.e. it
    contains no directory components or slashes. Every new file must have a
    unique new name.

    """
    __tablename__ = 'file'

    name = db.Column (db.String (256), primary_key=True)
    type = NotNull (db.String (32))
    create_time = NotNull (db.DateTime)
    obsid = db.Column (db.Integer, db.ForeignKey (Observation.obsid), nullable=False)
    source = NotNull (db.String (64))
    size = NotNull (db.Integer)
    md5 = NotNull (db.String (32))
    observation = db.relationship ('Observation', back_populates='files')
    instances = db.relationship ('FileInstance', back_populates='file')
    events = db.relationship ('FileEvent', back_populates='file')

    def __init__ (self, name, type, obsid, source, size, md5, create_time=None):
        if create_time is None:
            create_time = datetime.datetime.utcnow ()

        if '/' in name:
            raise ValueError ('illegal file name "%s": names may not contain "/"' % name)

        self.name = name
        self.type = type
        self.create_time = create_time
        self.obsid = obsid
        self.source = source
        self.size = size
        self.md5 = md5


    @property
    def create_time_unix (self):
        import calendar
        return calendar.timegm (self.create_time.timetuple ())


    def make_generic_event (self, type, **kwargs):
        """Create a new FileEvent record relating to this file. The new event is not
        added or committed to the database.

        """
        return FileEvent (self.name, type, kwargs)


    def make_instance_creation_event (self, instance, store):
        return self.make_generic_event ('create_instance',
                                        store_name=store.name,
                                        parent_dirs=instance.parent_dirs)


    def make_copy_launched_event (self, connection_name, remote_store_path):
        return self.make_generic_event ('launch_copy',
                                        connection_name=connection_name,
                                        remote_store_path=remote_store_path)


class FileInstance (db.Model):
    """A FileInstance is a copy of a File that lives on one of this Librarian's
    stores.

    Because the File record knows the key attributes of the file that we're
    instantiating (size, MD5 sum), a FileInstance record only needs to keep
    track of the location of this instance: its store, its parent directory,
    and the file name (which, because File names are unique, is a foreign key
    into the File table).

    Even though File names are unique, for organizational purposes they are
    sorted into directories when instantiated in actual stores. In current
    practice this is generally done by JD although this is not baked into the
    design.

    """
    __tablename__ = 'file_instance'

    store = db.Column (db.Integer, db.ForeignKey (Store.id), primary_key=True)
    parent_dirs = db.Column (db.String (128), primary_key=True)
    name = db.Column (db.String (256), db.ForeignKey (File.name), primary_key=True)
    file = db.relationship ('File', back_populates='instances')
    store_object = db.relationship ('Store', back_populates='instances')

    def __init__ (self, store_obj, parent_dirs, name):
        if '/' in name:
            raise ValueError ('illegal file name "%s": names may not contain "/"' % name)

        self.store = store_obj.id
        self.parent_dirs = parent_dirs
        self.name = name

    @property
    def store_name (self):
        return self.store_object.name

    @property
    def store_path (self):
        import os.path
        return os.path.join (self.parent_dirs, self.name)

    def full_path_on_store (self):
        import os.path
        return os.path.join (self.store_object.path_prefix, self.parent_dirs, self.name)


class FileEvent (db.Model):
    """A FileEvent is a something that happens to a File on this Librarian.

    Note that events are per-File, not per-FileInstance. One reason for this
    is that FileInstance records may get deleted, and we want to be able to track
    history even after that happens.

    On the other hand, FileEvents are private per Librarian. They are not
    synchronized from one Librarian to another and are not globally unique.

    The nature of a FileEvent payload is defined by its type. We suggest
    JSON-encoded text. The payload is limited to 512 bytes so there's only so
    much you can carry.

    """
    __tablename__ = 'file_event'

    id = db.Column (db.Integer, primary_key=True)
    name = db.Column (db.String (256), db.ForeignKey (File.name))
    time = NotNull (db.DateTime)
    type = db.Column (db.String (64))
    payload = db.Column (db.String (512))
    file = db.relationship ('File', back_populates='events')

    def __init__ (self, name, type, payload_struct):
        if '/' in name:
            raise ValueError ('illegal file name "%s": names may not contain "/"' % name)

        self.name = name
        self.time = datetime.datetime.utcnow ()
        self.type = type
        self.payload = json.dumps (payload_struct)


    @property
    def payload_json (self):
        return json.loads (self.payload)


# RPC endpoints

@app.route ('/api/create_file_event', methods=['GET', 'POST'])
@json_api
def create_file_event (args, sourcename=None):
    """Create a FileEvent record for a File.

    We enforce basically no structure on the event data.

    """
    file_name = required_arg (args, unicode, 'file_name')
    type = required_arg (args, unicode, 'type')
    payload = required_arg (args, dict, 'payload')

    file = File.query.get (file_name)
    if file is None:
        raise ServerError ('no known file "%s"', file_name)

    event = file.make_generic_event (type, **payload)
    db.session.add (event)
    db.session.commit ()
    return {}


# Web user interface

@app.route ('/files/<string:name>')
@login_required
def specific_file (name):
    file = File.query.get (name)
    if file is None:
        flash ('No such file "%s" known' % name)
        return redirect (url_for ('index'))

    instances = list (FileInstance.query.filter (FileInstance.name == name))
    events = sorted (file.events, key=lambda e: e.time, reverse=True)

    return render_template (
        'file-individual.html',
        title='%s File %s' % (file.type, file.name),
        file=file,
        instances=instances,
        events=events,
    )
