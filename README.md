git alot
========

`git status` for your `$HOME`.

![The alot, eating git](https://github.com/pwaller/git-alot/raw/master/doc/logo.png)

(Derived from [The Alot is better than you at everything](
    http://hyperboleandahalf.blogspot.co.uk/2010/04/alot-is-better-than-you-at-everything.html))


If you work on lots of git repositories across multiple machines, it is often
possible to lose track of the odd stash or untracked file. That is where the
alot comes in. He will rummage through and help you find those pesky untracked
files and lost stashes.


Quick start
-----------

You will need GitPython. If you have pip available, this is probably the
quickest way to get started:

```bash
pip install --user GitPython
```

Then put `git-alot.py` into a directory in your `$PATH` as `git-alot`.

Then type `git alot`.

If you have a cold filesystem cache you can expect this to take a few minutes
the first time you do it.


What does it do?
----------------

It will first find all directories called `.git` in your `$HOME`. Then it uses
[GitPython](https://github.com/gitpython-developers/GitPython) to find out what
uncommitted and untracked changes there are for each repository, along with
any stashes. It then lists all repositories with outstanding things.


Future concepts
---------------

It would be nice also to track of synchronizing repositories across multiple
machines, but I'm not sure how to implement this in a clean way at the moment,
other than just running it on each one and making sure for yourself that you
have pushed and fetched.


Issues
------

If you have any problems getting started, please [make an issue](
    https://github.com/pwaller/git-alot/issues/new). Pull requests are also welcome.
