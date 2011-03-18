#!/usr/bin/env python
#-*- coding: utf-8 -*-

# Author: youngtrips(youngtrips@gmail.com)
# Created Time:  2011-03-16
# File Name: test.py
# Description: 
#

import tempfile
import string
import sys
import os
import re
from svn import fs, repos, core, delta

import trac
import trac.env
import trac.wiki
import trac.wiki.admin

from rst2wiki import rst2wiki

class ChangedEditor(delta.Editor):
	def __init__(self, root, base_root):
		self.root = root
		self.base_root = root
		self.deltas = []

	def open_root(self, base_revision, dir_pool):
		return [ 1, '' ]
	
	def delete_entry(self, path, revision, parent_baton, pool):
		if fs.is_dir(self.base_root, '/' + path):
			self.deltas.append(('D', path + '/'))
		else:
			self.deltas.append(('D', path))

	def add_directory(self, path, parent_baton,
                    copyfrom_path, copyfrom_revision, dir_pool):
		self.deltas.append(('A', path + '/'))
		return [ 0, path ]
		
	def open_directory(self, path, parent_baton, base_revision, dir_pool):
		return [ 1, path ]

	def change_dir_prop(self, dir_baton, name, value, pool):
		if dir_baton[0]:
			dir_baton[0] = 0
	
	def add_file(self, path, parent_baton, 
			copyfrom_path, copyfrom_revision, file_pool):
		self.deltas.append(('A', path))
		return [ '_', ' ', None ]
		
	def open_file(self, path, parent_baton, base_revision, file_pool):
		return [ '_', ' ', path ]
		
	def apply_textdelta(self, file_baton, base_checksum):
		file_baton[0] = 'U'
		if file_baton[2]:
			self.deltas.append(('U', file_baton[2]))
		return None

class RstFilter:
	def __init__(self, filter_path):
		pattern = r"^%s/[a-z,A-Z,0-9,/]*\.rst$" % filter_path
		self.p = re.compile(pattern)
	def check(self, filename):
		if self.p.match(filename):
			return True
		return False

class SvnController:
	def __init__(self, repos_path, rev, rstfilter):
		self.rst_changes = []
		repos_path = core.svn_path_canonicalize(repos_path)
		repos_ptr = repos.open(repos_path)
		self.fs_ptr = repos.fs(repos_ptr)
		self.rev = rev
		self.rstfilter = rstfilter

	def get_author(self):
		author = fs.revision_prop(self.fs_ptr, self.rev, core.SVN_PROP_REVISION_AUTHOR) or ''
		return author

	def get_changes(self):
		base_rev = self.rev - 1
		#get the current root
		root = fs.revision_root(self.fs_ptr, self.rev)
		#the base of comparison
		base_root = fs.revision_root(self.fs_ptr, base_rev)
		editor = ChangedEditor(root, base_root)
		e_ptr, e_baton = delta.make_editor(editor)
		def authz_cb(root, path, pool):
			return 1
		repos.dir_delta(base_root, '', '', root, '',
				e_ptr, e_baton, authz_cb, 0, 1, 0, 0)

		for elem in editor.deltas:
			if self.rstfilter.check(elem[1]):
				self.rst_changes.append(elem)

	def get_rst_changes(self):
		return self.rst_changes

	def get_file(self, filename, rev=None):
		CHUNK_SIZE = 16384
		root = fs.revision_root(self.fs_ptr, self.rev)
		file = fs.file_contents(root, filename)
		data = ""
		while True:
			tmp = core.svn_stream_read(file, CHUNK_SIZE)
			if not tmp:
				break
			data = data + tmp
		return data

"""change rst file which in target path to wiki format,
	them put them to trac
"""
class Controller:
	def __init__(self, repos_path, rev, trac_path, rst_path):
		self.rst_path = rst_path
		self.rev = rev
		self.trac_path = trac_path
		self.rst_path = rst_path
		self.rstfilter = RstFilter(rst_path)
		self.svnctl = SvnController(repos_path, rev, self.rstfilter)
		self.env = trac.env.Environment(self.trac_path)
		self.wikiadmin = trac.wiki.admin.WikiAdmin(self.env)
		self.wikisystem = trac.wiki.api.WikiSystem(self.env)
		tempfile.tempdir = "/tmp"
		self.author = self.svnctl.get_author()

	def import_wiki(self, filename, replace_flag=False):
		input = self.svnctl.get_file(filename, self.rev)
		output = rst2wiki(input)
		name = string.split(filename, self.rst_path)[1]
		wikititle = ''.join(name.split('/')).split('.')[0]

		page = trac.wiki.model.WikiPage(self.env, wikititle)
		page.text = output
		page.save(self.author, "", "127.0.0.1")

	def A_wiki(self, filename):
		self.import_wiki(filename)

   	def U_wiki(self, filename):
		self.import_wiki(filename)

	def D_wiki(self, filename):
		name = string.split(filename, self.rst_path)[1]
		wikititle = ''.join(name.split('/')).split('.')[0]
		page = trac.wiki.model.WikiPage(self.env, wikititle)
		page.delete()

	def main(self):
		self.svnctl.get_changes()
		rst_changes = self.svnctl.get_rst_changes()
		for elem in rst_changes:
			if elem[0] in ['A', 'D', 'U']:
				getattr(self, elem[0] + '_wiki')(elem[1])

if __name__ == "__main__":
	repos_path = sys.argv[1]
	rev = int(sys.argv[2])
	trac_path = sys.argv[3]
	rst_path = sys.argv[4]

	ctl = Controller(repos_path, rev, trac_path, rst_path)
	ctl.main()
