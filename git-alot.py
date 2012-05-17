#! /usr/bin/env python

from os import environ, makedirs, stat
from os.path import abspath, exists, expandvars, join as pjoin
from subprocess import Popen, PIPE
from textwrap import dedent

import re
import sys

import git

old_hook = sys.excepthook
def gitalot_hook(*args, **kwargs):
    result = old_hook(*args, **kwargs)
    exception_type, instance, traceback = args
    if not isinstance(instance, KeyboardInterrupt):
        print
        print "Please make an issue with the contents of the backtrace:"
        print "https://github.com/pwaller/git-alot/issues/new"
    return result
sys.excepthook = gitalot_hook

# Match the output of "git branch -vva"
RE_BRANCH = re.compile(dedent(r"""
    ^(?P<active>\*)?\s*
    (?P<branch>(\(no\ branch\)|[^\s]+))\s+
    (
        (
         (?P<sha>[0-9a-f]+)\s+
         (\[
            (?P<tracking>[^\:]+):?\s*
            (ahead\s+(?P<ahead>[0-9]+),?)?\s*
            (behind\s+(?P<behind>[0-9]+))?\s*
            (?P<unmatched>[^\]]+)?\s*
          \]\s+
         )?
         (?P<msg>.*)
        )
        |
        (->\s+(?P<sym>.*))
    )\s*$"""), re.VERBOSE)

def parse_branch_output(output):
    result = []
    for line in [l for l in output.split("\n") if l]:
        m = RE_BRANCH.match(line)
        if not m: raise RuntimeError("Unmatched: {0!r} {1}".format(line, output))
        result.append(m.groupdict())
    return result

# TODO

# Repository 'cleanliness' for sorting
# Remote syncing status?
# Find roots of repositories, so that repository copies can be identified?
# Commandline switches (e.g, only view stashes, or other things)


def find_git_repositories(base):
    base = base or environ["HOME"]
    args = ["find", base, "-type", "d", "-iname", ".git"]
    p = Popen(args, stdout=PIPE, stderr=PIPE)
    output, stderr = p.communicate()
    if p.returncode != 0:
        print "Find may not have found all repositories: {0}".format(stderr)
    return output.strip().split("\n")

def indent(t, i=4):
    i = " "*i
    return i + ("\n"+i).join(t.split("\n"))
    
class AlotRepo(object):
    def __init__(self, path, prev_mtime=None):
        self.repo = git.Repo(path)
        self._branch_data = None
        self.prev_mtime = prev_mtime
    
    def __lt__(self, rhs):
        # TODO some sort of cleanliness metric?
        return self.repo.working_dir < rhs.repo.working_dir
    
    @property
    def no_commits(self):
        return not self.repo.refs
    
    @property
    def path(self):
        r = self.repo
        return r.git_dir if r.bare else r.working_dir 
    
    @property
    def mtime(self):
        return stat(self.path).st_mtime
    
    @property
    def stale(self):
        if self.prev_mtime is not None:
            return True
        return self.prev_mtime <= self.mtime
    
    def branches(self, *args):
        return parse_branch_output(self.repo.git.branch(*args))
        
    @property
    def branch_data(self):
        if self._branch_data is None:
            try:
                total = self.branches("-vva")
                merged = self.branches("-vv", "--merged")
                nomerged = self.branches("-vv", "--no-merged")
            except git.exc.GitCommandError:
                total, merged, nomerged = [], [], []
            
            active = None
            for branchdata in total:
                if branchdata["active"]:
                    active = branchdata["branch"]
            
            self._branch_data = active, total, merged, nomerged
            
        return self._branch_data
    
    @property
    def has_stash(self):
        return "refs/stash" in self.repo.refs
    
    @property
    def has_dirt(self):
        repo, o = self.repo, self.options
        if self.no_commits:
            return True
        if o.worktree and repo.is_dirty(index=False):
            return True
        if o.index and repo.is_dirty(working_tree=False):
            return True
        if o.untracked and repo.untracked_files:
            return True
        if o.stashes and self.has_stash:
            return True
        if o.branches:
            # TODO: actual detection of dirt
            return True
        return False
    
    def __str__(self):
        result = []; A = result.append
        repo = self.repo
        
        A(repo.working_dir)
        
        if self.no_commits:
            A("  !! NO COMMITS !!")
            return "\n".join(result)
        
        if self.options.worktree and repo.is_dirty(index=False):
            A("  == Dirty Working Tree ==")
            A(indent(repo.git.diff(stat=True), i=3))
            
        if self.options.index and repo.is_dirty(working_tree=False):
            A("  == Dirty Index (stuff to commit!) ==")
            A(indent(repo.git.diff(stat=True, cached=True), i=3))
        
        if self.options.untracked:
            untracked = repo.untracked_files
            if untracked:
                A("  == {0} Untracked file(s) ==".format(len(untracked)))
                MAX = 10
                A(indent("\n".join(untracked[:MAX])))
                if len(untracked) > MAX:
                    A(indent("... and {0} more".format(len(untracked)-MAX)))
        
        if self.options.stashes and self.has_stash:
            try:
                log = repo.refs["refs/stash"].log()
            except ValueError:
                # GitPython workaround
                A(indent("!! Problem reading stash !!"))
                log = []
                pass
            
            A("  == {0} item(s) in stash ==".format(len(log)))
            for i, stash in enumerate(log):
                A(indent(stash.message))
                ref = "stash@{{{0}}}".format(i)
                A(indent(repo.git.stash("show", "--stat", ref), 7))
        
        if self.options.branches:
            A("  == unclean branch state ==")
            # Unclean branch states
            # * not being on master or dev
            # * branches are ahead/behind
            # * branches are merged
            # * branches are unmerged
            active, total, merged, unmerged = self.branch_data
            if active is None or active.startswith("(") and active.endswith(")"):
                A(indent("Not on a branch!"))
            elif active not in set(("master", "dev")):
                A(indent("Not on master or dev!"))
            A(indent("Active branch: {0}".format(active)))
        
        return "\n".join(result)

def parse_args(args):
    from optparse import OptionParser
    parser = OptionParser("git alot [options] [base directory]\n\n"
        "The git alot can help you with a lot of repositories.")
    O = parser.add_option
    
    switches = dict(
        worktree="w",
        index="i",
        untracked="u",
        stashes="s",
        branches="b",
    )
    for switch, small in sorted(switches.iteritems()):
        small = "-" + small
        O("--{0}".format(switch), small, action="store_true", dest=switch)
        O("--no-{0}".format(switch), small.upper(), action="store_false", dest=switch)
    
    O("-f", "--fetch", action="store_true",
        help="Run git fetch --all for all matching repositories")
        
    O("-c", "--update-cache", action="store_true")
    O("--updated", action="store_true",
      help="Only show repositories modified since the cache was generated")
    
    options, args = parser.parse_args(args)
    
    specific = any(getattr(options, s) for s in switches)

    # If no specific dirt-type is selected, enable all unspecified ones
    if not specific:
        for s in switches:
            if getattr(options, s) is None:
                setattr(options, s, True)
    
    if not args:
        base = None
    elif len(args) == 1:
        base = args[0]
    else:
        print >>sys.stderr, "Error: unused arguments: ", args[1:]
        print parser.usage()
        raise SystemExit(1)
    
    return options, base

def cachedir():
    base = environ.get("XDG_CACHE_HOME", pjoin(environ.get("HOME"), ".cache"))
    path = pjoin(base, "git", "alot")
    if not exists(path):
        makedirs(path)
    return path

def main():
    options, base = parse_args(sys.argv[1:])
    
    AlotRepo.options = options

    cachefile = pjoin(cachedir(), "cache")
    if options.update_cache or not exists(cachefile) or base is not None:
        print "Searching for repositories..",
        sys.stdout.flush()
        repos = find_git_repositories(base)
        if base is not None:
            # Only generate the cache if we are doing the whole of HOME
            # (base is None)
            with open(cachefile, "w") as fd:
                # TODO write mtimes
                fd.write("\n".join(repos))
    else:
        with open(cachefile) as fd:
            repos = fd.read().split("\n")
        if base is None: base = environ["HOME"]
        
        repos = [AlotRepo(path, prev_mtime) for prev_mtime, path in lines
                 if path.startswith(abspath(base))]
    
    repos = [r for r in repos if not r.repo.bare]
    
    if options.updated:
        repos = [r for r in repos if not r.stale]
    
    print "Found {0}. That's alot of git.".format(len(repos))
    
    
    if options.fetch:
        for repo in repos:
            print "Fetching for", repo
            repo.git.fetch("--all")
        return 0
    
    dirty_repos = [r for r in repos if r.has_dirt]
    dirty_repos.sort()
    
    for repo in dirty_repos:
        try:
            print repo
        except:
            print "Encountered a problem ", repo.repo
            raise
        print
    
    nrepos = len(repos)
    nclean = len(repos) - len(dirty_repos)
    if nclean == nrepos:
        print """                                       ?IIMIM?
      _____________   =M   M777II7I77777Z   =+M
     /             \   D?I77I7II7IIIIII7777Z++
    | Alot didn't   |    I77IIOIIIIII7III78
    | find anything |    7$ o  I77MMMMM o ~M8N
    | out of place /     ,ZIIM$7I7IIII7$$MONN7I$$$$$$$$OM?
    \_____________/ `-- III787I       IIIINIII$77ZZ$$7Z$$$7NZMM?M
                        IIM$I IIIIIIIII III$MI77$77$7I7$$$$$$$$$Z$O
                       OIIM  IIIIIIIIIII  II7MI777$$$$Z7$$$$$$$77$77$~
                      MIIIIIIIIIIIIIIIIIIIIII7777$$$7$$$$I$7$7$$77$77$I
                      MIIIIIIIIIIIIIIIIIIIIIIII77$7$I7$I$$7ZI77$77$I77:?
                     O$???IIIIIIIIIIIIIIIIIIIIII777I7777777I77777777I7IN
                     MM7??IIIIIIIIIIIIIIIIII??II77I77II7I7I7777777I77I77N:
                      :~M$7???IIIIIIII????+?IIII7I7777II77II??II77777?I?II
                        O77I???????????+++?IIII?I?77IIII?I??+?++IIIIIIIII7
                        :N????I??????++?+?IIIII????IIIIIII??????I++I?7I7IIO
                        7ZZI???+?++++IIIIIIIIIII?II??????I?+IIIIII+I??IIIII
                        M$ZN$77?+?++=IDIIIIIIIO7?I?+?+????+8?IIIIIII?IIIIII
                       MII7$$Z7II7?7I$$IIIIIIII$I?????????I777IIIIIIIIIIIIIIM
                      MIIIIIIIMM$MIIII77IIIIIII$7?I??I???????I$IIIIIIIIIIIIII
                      IIIIIIII     $II7MIIIIIIIIM7I????????IID$ZIIIIIIIIIIIII
                     MM                MMMIIMIMMM ~  DM M?   ~  ?IMM$MMM  M
                                        M   M ?"""
        return 0
    elif nclean >= 0.75*nrepos:
        print ".. you have {0} clean repositories out of {1}. Nice!".format(nclean, nrepos)
    elif nclean >= 0.5*nrepos:
        print ".. you have {0} clean repositories out of {1}. Good!".format(nclean, nrepos)
    elif nclean >= 0.25*nrepos:
        print ".. you have {0} clean repositories out of {1}.".format(nclean, nrepos)
    elif nclean > 0:
        print ".. only {0} of your {1} repositories are clean.".format(nclean, nrepos)
    else:
        print "You have no clean repositories out of {0} :-(".format(nrepos)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
