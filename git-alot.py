#! /usr/bin/env python

from os.path import expandvars
from commands import getstatusoutput

import git

# TODO

# * Stashes
# * Repository 'cleanliness'
# * Find roots of repositories, so that repository copies can be identified?
# * Remote syncing status?

def find_git_repositories():
    status, output = getstatusoutput(expandvars("find ${HOME} -iname .git"))
    assert not status, "Find failed: {0}".format(output)
    return output.split("\n")

def indent(t, i=4):
    i = " "*i
    return i + ("\n"+i).join(t.split("\n"))
    
class AlotRepo(object):
    def __init__(self, repo):
        self.repo = repo
    
    def __lt__(self, rhs):
        # TODO some sort of cleanliness metric?
        return self.repo.working_dir < rhs.repo.working_dir
    
    @property
    def has_stash(self):
        return "refs/stash" in self.repo.refs
    
    @property
    def has_dirt(self):
        # TODO check for stash
        return self.repo.is_dirty(untracked_files=True) or self.has_stash
    
    def __str__(self):
        result = []; A = result.append
        repo = self.repo
        
        A(repo.working_dir)
        
        if repo.is_dirty(index=False):
            A("  == Dirty Working Tree ==")
            A(indent(repo.git.diff(stat=True), i=3))
            
        if repo.is_dirty(working_tree=False):
            A("  == Dirty Index (stuff to commit!) ==")
            A(indent(repo.git.diff(stat=True, cached=True), i=3))
            
        untracked = repo.untracked_files
        if untracked:
            A("  == {0} Untracked file(s) ==".format(len(untracked)))
            MAX = 10
            A(indent("\n".join(untracked[:MAX])))
            if len(untracked) > MAX:
                A(indent("... and {0} more".format(len(untracked)-MAX)))
        
        if self.has_stash:
            log = repo.refs["refs/stash"].log()
            
            A("  == {0} item(s) in stash ==".format(len(log)))
            for i, stash in enumerate(log):
                A(indent(stash.message))
                ref = "stash@{{{0}}}".format(i)
                A(indent(repo.git.stash("show", "--stat", ref), 7))
                
        
        return "\n".join(result)
    
def main():
    print "Searching for repositories..",
    repos = find_git_repositories()
    print "Found {0}. That's alot of git.".format(len(repos))
    
    repos = map(git.Repo, repos)
    repos = [r for r in repos if not r.bare]
    
    repos = map(AlotRepo, repos)
    dirty_repos = [r for r in repos if r.has_dirt]
    dirty_repos.sort()
    
    for repo in dirty_repos:
        print repo
        print
    
    nrepos = len(repos)
    nclean = len(repos) - len(dirty_repos)
    if nclean == nrepos:
        print "All of your {0} repositories are clean. Very Nice!".format(nrepos)
    elif nclean >= 0.75*nrepos:
        print ".. you have {0} clean repositories out of {1}. Nice!".format(nclean, nrepos)
    elif nclean >= 0.5*nrepos:
        print ".. you have {0} clean repositories out of {1}. Good!".format(nclean, nrepos)
    elif nclean >= 0.25*nrepos:
        print ".. you have {0} clean repositories out of {1}.".format(nclean, nrepos)
    elif nclean > 0:
        print ".. only {0} of your {1} repositories are clean.".format(nclean, nrepos)
    else:
        print "You have no clean repositories :-("

if __name__ == "__main__":
    main()
