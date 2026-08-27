# The commit map

On 2026-08-27 this repository's history was rewritten with `git filter-repo` to
remove ten publisher rasters and eleven PNGs cut from them. They were tracked
here from the first commits while `README.md` said "private research
repository" and GitHub said `visibility: public`. Removing them from the tree
stops the distribution going forward; removing them from the history is what
stops `git clone` from handing them to the next person.

Every commit was rewritten, so **every SHA in this repository's own records
changed**. That is a real cost: `INSTALL.md` is a release history and cites the
commit each release landed in, `experiments/*.json` name the commit their
measurement was taken on, and commit messages refer to earlier commits by SHA.
A rewrite that silently invalidates all of them trades one kind of dishonesty
for another.

So the map is kept. `commit-map.tsv` is `git filter-repo`'s own output: one line
per commit, `old<TAB>new`, 197 of them. To resolve a SHA written down before the
rewrite:

    grep ^<old-sha> history/commit-map.tsv

The pre-rewrite history itself is not published - it is the thing being removed.
It exists as a bundle outside this repository, held by the maintainer, so a
claim about what an old commit contained can still be checked by someone with
access to it.

## The SHAs this package's own files cite

| written down as | after the rewrite |
| --- | --- |
| `28a74a9` | `3dd094f` |
| `2f481aa` | `f6c5c15` |
| `4397cad` | `8c27d10` |
| `599dbb8` | `5621e4f` |
| `5a11b5f` | `f20e00a` |
| `65a781a` | `22a495d` |
| `74e6b44` | `e28b536` |
| `88dba15` | `442ce09` |
| `ae45ece` | `e43cef2` |
| `b9b33af` | `1afc606` |
| `c83dd01` | `5dc23f9` |
| `cc37f4e` | `ec41edf` |
| `d1a77f4` | `1eb2ad8` |
| `e10b316` | `778c24a` |
| `7a588f5` | `87d7945` |
| `91f024d` | `b6d76bd` |
| `e3864c9` | `830bffa` |

The prose was NOT rewritten to the new SHAs. A record says what was true when it
was written, and a release history edited to match today is not a history. This
table and `commit-map.tsv` are how the old numbers stay resolvable.

## What was removed

`purge-paths.txt` is the exact list passed to `git filter-repo --invert-paths`.
Every one of the ten rasters is still pinned by SHA-256 in `raster_root.py`, so
a reader who has the originals can confirm that what they hold is what this
package measured — which is the part of reproducibility that survives not
shipping the figures.
