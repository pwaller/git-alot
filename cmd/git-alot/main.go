package main

import (
	"bufio"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"

	"github.com/pwaller/fastwalk"
)

// Repo represents a git repository
type Repo struct {
	Dir, WorkTree string
}

// NewRepo constrcts a repo from a .git dir or file.
func NewRepo(dotGit string, typ os.FileMode) (Repo, error) {
	if typ.IsRegular() {
		dir, ok := getGitDir(dotGit)
		if !ok {
			return Repo{}, fmt.Errorf("not a git dir: %q", dotGit)
		}
		// When `.git` is a file contianing `gitdir:`,
		// e.g. for submodules.
		return Repo{
			Dir:      dir,
			WorkTree: filepath.Dir(dotGit),
		}, nil
	}
	return Repo{
		Dir:      dotGit,
		WorkTree: filepath.Dir(dotGit),
	}, nil
}

// GitStatus represents the output of `git status`
type GitStatus struct {
	Files map[string][]string
}

// NewGitStatus constructs a GitStatus
func NewGitStatus(path string) GitStatus {
	cmd := exec.Command("git", "status", "--porcelain")
	cmd.Dir = path
	cmd.Stderr = os.Stderr

	stdout, err := cmd.StdoutPipe()
	if err != nil {
		log.Fatal(err)
	}

	err = cmd.Start()
	if err != nil {
		log.Fatal(err)
	}

	s := bufio.NewScanner(stdout)
	files := map[string][]string{}

	for s.Scan() {
		fields := strings.Fields(s.Text())
		first, second := fields[0], fields[1]
		fullPath := filepath.Join(path, second)
		if filepath.Dir(fullPath) == filepath.Base(fullPath) && first == "??" {
			// Special case: skip untracked files named after the
			// directory they're in, since they're probably go
			// binaries.
			continue
		}
		files[first] = append(files[first], second)
	}
	if err = s.Err(); err != nil {
		log.Fatal(err)
	}

	err = cmd.Wait()
	if err != nil {
		log.Fatal(err)
	}

	return GitStatus{
		Files: files,
	}
}

func main() {
	repos, err := listRepositories(".")
	if err != nil {
		log.Fatal(err)
	}

	for _, repo := range repos {
		if !hasRemotes(repo.Dir) {
			log.Printf("No remotes: %q", repo)
		}
		st := NewGitStatus(repo.WorkTree)
		if len(st.Files) == 0 {
			// It's clean
			continue
		}
		log.Println(repo)
		for k, v := range st.Files {
			log.Printf("  %q: %v", k, len(v))
		}
	}
}

func hasRemotes(repo string) bool {
	remotes := filepath.Join(repo, "refs", "remotes")
	_, err := os.Stat(remotes)
	if os.IsNotExist(err) {
		return false
	}
	if err != nil {
		log.Fatal(err)
	}
	return true
}

func listRepositories(path string) ([]Repo, error) {
	var (
		mu    sync.Mutex
		repos []Repo
	)

	err := fastwalk.Walk(path, func(path string, typ os.FileMode) error {
		if filepath.Base(path) != ".git" {
			return nil
		}
		repo, err := NewRepo(path, typ)
		if err != nil {
			log.Printf("Failed for %q: %v", path, err)
			return nil
		}
		mu.Lock()
		repos = append(repos, repo)
		mu.Unlock()
		return nil
	})

	sort.Sort(ByWorkTree(repos))

	return repos, err
}

// ByWorkTree sorts by worktree
type ByWorkTree []Repo

func (a ByWorkTree) Len() int           { return len(a) }
func (a ByWorkTree) Swap(i, j int)      { a[i], a[j] = a[j], a[i] }
func (a ByWorkTree) Less(i, j int) bool { return a[i].WorkTree < a[j].WorkTree }

func getGitDir(path string) (string, bool) {
	content, err := ioutil.ReadFile(path)
	if err != nil {
		return "", false
	}

	var re = regexp.MustCompile("^gitdir: (.*)")
	submatches := re.FindStringSubmatch(string(content))
	if len(submatches) == 0 {
		return "", false
	}
	relPath := string(submatches[1])
	path = filepath.Clean(filepath.Join(filepath.Dir(path), relPath))
	return path, true
}
