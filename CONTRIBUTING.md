# How to contribute

Many thanks for considering contributing to OpenRVDAS.

#### Table Of Contents
- [Code of Conduct](#code-of-conduct)
- [I just have a question!!!](#i-just-have-a-question!!!)
- [What should I know before I get started?](#what-should-i-know-before-i-get-started?)
- [How Can I Contribute?](#how-can-i-contribute?)
  - [Reporting Bugs](#reporting-bugs)
    - [Before Submitting A Bug Report](#before-submitting-a-bug-report)
    - [How Do I Submit A (Good) Bug Report?](#how-do-i-submit-a-(good)-bug-report?)
  - [Suggesting Enhancements](#suggesting-enhancements)
    - [Before Submitting An Enhancement Suggestion](#before-submitting-an-enhancement-suggestion)
    - [How Do I Submit A (Good) Enhancement Suggestion?](#how-do-i-submit-a-(good)-enhancement-suggestion?)
  - [Contributing Code](#contributing-code)
    - [If you have a bug fix.](#if-you-have-a-bug-fix.)
    - [If you have a feature or code module you would like to add.](#if-you-have-a-feature-or-code-module-you-would-like-to-add.)
    - [If you would just like to help out somewhere.](#if-you-would-just-like-to-help-out-somewhere.)
  - [Git Commits and Pull Requests](#git-commits-and-pull-requests)
    - [Unit tests](#unit-tests)
    - [flake8](#flake8)
    - [Commits](#commits)
    - [Pull requests](#pull-requests)
- [Styleguides](#styleguides)
  - [Python Styleguide](#python-styleguide)
  - [JavaScript Styleguide](#javascript-styleguide)
  - [Documentation Styleguide](#documentation-styleguide)

## Code of Conduct

This project and everyone participating in it is governed by the [OpenRVDAS Code of Conduct](CODE_OF_CONDUCT.md). By 
participating, you are expected to uphold this code. Please report unacceptable behavior to 
[oceandatatools@github.com](mailto:oceandatatools@github.com).

## I just have a question!!!

> **Note:** Please don't file an issue to ask a question. You'll get faster results by using the resources below.

* If you haven't already, please join the [OpenRVDAS mailing list](https://groups.google.com/forum/#!forum/openrvdas).
* If chat is more your speed, please join the [OpenRVDAS Discord channel](https://discord.gg/8n7HSwf5ZV) to ask your questions there.
    * Even though Discord is a chat service, sometimes it takes several hours for community members to respond &mdash; please be patient!
    * Use the `#general` channel for general questions or discussion about OpenRVDAS
    * Use the `#openrvdas` channel for technical questions about OpenRVDAS

## What should I know before I get started?

OpenRVDAS is largely a volunteer effort. Most folks involved in the project have demanding day jobs and are supporting the
code in their spare time. They may not be able to respond quickly and comprehensively to every question.

The OpenRVDAS architecture is intended to be modular, extensible and as platform-independent as practical. Contributors should
consider how their proposed changes will affect the 

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for OpenRVDAS. Following these guidelines helps maintainers and
the community understand your report, reproduce the behavior, and find related reports.

Before creating bug reports, please check [this list](#before-submitting-a-bug-report) as you might find out that you
don't need to create one. When you are creating a bug report, please
[include as many details as possible](#how-do-i-submit-a-good-bug-report). Fill out 
the required template, the information it asks for helps us resolve issues faster.

> **Note:** If you find a **Closed** issue that seems like it is the same thing that you're experiencing, open a new
issue and include a link to the original issue in the body of your new one.

#### Before Submitting A Bug Report

* **Perform a [cursory search](https://github.com/oceandatatools/openrvdas/issues)** to see if the problem has already been
  reported. If it has **and the issue is still open**, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Bug Report?

Bugs are tracked as [GitHub issues](https://guides.github.com/features/issues/).
Explain the problem and include additional details to help maintainers reproduce the problem:

* **Use a clear and descriptive title** for the issue to identify the problem.
* **Describe the exact steps which reproduce the problem** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include links to files or GitHub projects, or copy/pasteable snippets, which you use in those examples. If you're providing snippets in the issue, use [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the behavior you observed after following the steps** and point out what exactly is the problem with that behavior.
* **Explain which behavior you expected to see instead and why.**
* **If the problem is related to performance or memory**, include a CPU profile capture if able.
* **If the problem wasn't triggered by a specific action**, describe what you were doing before the problem happened and share more information using the guidelines below.

Provide more context by answering these questions:

* **Did the problem start happening recently** (e.g. after updating to a new version) or was this always a problem?
* **Can you reliably reproduce the issue?** If not, provide details about how often the problem happens and under which conditions it normally happens.

Include details about your configuration and environment:

* **Which version of the code are you using?** 
* **What's the name and version of the OS you're using**?
* **Are you running OpenRVDAS in a virtual machine?** If so, which VM software are you using and which operating systems and versions are used for the host and the guest?

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for OpenRVDAS, including completely new features and minor improvements to existing functionality. Following these guidelines helps maintainers and the community understand your suggestion and find related suggestions.

Before creating enhancement suggestions, please check [this list](#before-submitting-an-enhancement-suggestion) as you might find out that you don't need to create one. When you are creating an enhancement suggestion, please [include as many details as possible](#how-do-i-submit-a-good-enhancement-suggestion). Fill in [the template](https://github.com/atom/.github/blob/master/.github/ISSUE_TEMPLATE/feature_request.md), including the steps that you imagine you would take if the feature you're requesting existed.

#### Before Submitting An Enhancement Suggestion

* **Perform a [cursory search](https://github.com/oceandatatools/openrvdas/issues)** to see if the enhancement has already been suggested. If it has, add a comment to the existing issue instead of opening a new one.

#### How Do I Submit A (Good) Enhancement Suggestion?

Enhancement suggestions are tracked as [GitHub issues](https://guides.github.com/features/issues/). After you've determined [which repository](#atom-and-packages) your enhancement suggestion is related to, create an issue on that repository and provide the following information:

* **Use a clear and descriptive title** for the issue to identify the suggestion.
* **Provide a step-by-step description of the suggested enhancement** in as many details as possible.
* **Provide specific examples to demonstrate the steps**. Include copy/pasteable snippets which you use in those examples, as [Markdown code blocks](https://help.github.com/articles/markdown-basics/#multiple-lines).
* **Describe the current behavior** and **explain which behavior you expected to see instead** and why.
* **Explain why this enhancement would be useful** to OpenRVDAS users.

### Contributing Code

#### If you have a bug fix.

If you have a bug fix that you believe should be integrated back into the core repository,
please [issue a pull request to integrate it into the OpenRVDAS __dev__ branch](https://github.com/OceanDataTools/openrvdas/pulls)
(_not_ master). If it fixes a previously reported issue, please make sure your pull request references the issue number in question.

If it fixes an issue that has _not_ been previously reported, please [file an issue report](https://github.com/OceanDataTools/openrvdas/issues) prior to sending the pull request.
The issue report will be a much better forum for explaining what the problem is than whatever you put in the text of your
pull request, and will allow discussion of the problem and its resolution.

#### If you have a feature or code module you would like to add.

There is now a separate [openrvdas_contrib repository](https://github.com/OceanDataTools/openrvdas_contrib). We encourage you to create new modules
in the `contrib/` subdirectory of that repository, following the conventions described in [contrib/README.md](contrib/README.md)

If you would like to make the case that this feature should should be incorporated into the core repository, please file an "Enhancement Request", as above.

#### If you would just like to help out somewhere.

Unsure where to begin contributing to OpenRVDAS? You can start by looking through these `good first issue` and `help-wanted` issues:

* [Good first issue](good-first-issue) - issues which should only require a few lines of code, and a test or two.
* [Help wanted issues](help-wanted) - issues which should be a bit more involved than `beginner` issues.

Both issue lists are sorted by total number of comments. While not perfect, number of comments is a reasonable proxy for impact a given change will have.

When your contribution is ready:
, ensure that
```
git branch issue_57
git checkout issue_57
```

When your contribution is ready, submit a pull request, requesting that it be merged back into the OpenRVDAS ``dev`` branch. The ``dev`` branch will be merged into the ``master`` branch when new numbered versions are released.

### Git Commits and Pull Requests

Prior to submitting any pull request, please ensure that the code 1) passes all unit tests, and 2) produces no complaints under flake8. 

#### Unit tests

A commit for any new module or functionality should, if at all possible, be accompanied by a new unit test. Remember:
unit tests are what your teeth feel like after you floss. Write them!

You should also verify that your change does not break any pre-existing code by running all the rest of the repository's unit tests.
To run using Django's test mechanism (which will include any Django-specific tests), run:

```
./manage.py test
```

If, for some reason you don't want to run the Django-related tests, you can run everything elso with:
```
python -m unittest discover
```

#### flake8

Flake8 is a PEP8 Style Guide checker. Install using `pip install flake8` in the OpenRVDAS virtual environment, then test using

```buildoutcfg
flake8
```
on the command line. As referenced in the Style Guide below, we allow certain deviations from flake8 recommendations, but the
warnings these variations trigger must be silence by appropriate use of `noqa` comments.

#### Commits

Always write a clear log message for your commits. One-line messages are fine for small changes, but bigger changes
should look like this:

    $ git commit -m "A brief summary of the commit
    > 
    > A paragraph describing what changed and its impact."

#### Pull requests
Please file a GitHub  [pull request for oceandatatools/openrvdas/dev](https://github.com/oceandatatools/openrvdas/pull/new/dev) (or for [oceandatatools/openrvdas/dev](https://github.com/oceandatatools/openrvdas_contrib/pull/new/dev) as appropriate), with
a clear list of what you've done (read more about [pull requests](http://help.github.com/pull-requests/)). When you send
a pull request, we will love you forever if you include examples. We can always use more test coverage. Please follow
our coding conventions (below) and make sure all of your commits are atomic (one feature per commit).

## Styleguides

### Python Styleguide

* With few exceptions, we try to adhere to PEP8 and the [Google Python Style Guide](http://google.github.io/styleguide/pyguide.html)
* The primary exceptions are
   * We (grudgingly) allow a maximum line length of 100 characters
   * All unqualified imports (``import foo``) are clustered alphabetically before qualified imports (``from foo import bar``).
* We test code compliance with PEP8 with `flake8`
  * Install flake8 with `pip install flake8`
  * Run from project root with `flake8 [subdir path]`
  * Add pragma comments to disable warnings on a line-by-line basis, e.g.
  
      ```from foo import bar  # noqa: E401, F502```
* Do not mix styles: when editing a pre-existing file, strive for consistency with the file's style over adherence with the Style Guide.
 
### JavaScript Styleguide

All JavaScript must adhere to [JavaScript Standard Style](https://standardjs.com/).

* Prefer the object spread operator (`{...anotherObj}`) to `Object.assign()`
* Inline `export`s with expressions whenever possible
  ```js
  // Use this:
  export default class ClassName {

  }

  // Instead of:
  class ClassName {

  }
  export default ClassName
  ```

* Place class properties in the following order:
    * Class methods and properties (methods starting with `static`)
    * Instance methods and properties
* Use `count + 1` instead of `count+1`
* Use spaces after commas (unless separated by newlines)
* Use parentheses if it improves code clarity.
* Prefer alphabetic keywords to symbolic keywords:
    * `a is b` instead of `a == b`
* Avoid spaces inside the curly-braces of hash literals:
    * `{a: 1, b: 2}` instead of `{ a: 1, b: 2 }`
* Include a single line of whitespace between methods.
* Capitalize initialisms and acronyms in names, except for the first word, which
  should be lower-case:
  * `getURI` instead of `getUri`
  * `uriToOpen` instead of `URIToOpen`
* Use `slice()` to copy an array
* Add an explicit `return` when your function ends with a `for`/`while` loop and
  you don't want it to return a collected array.
* Use `this` instead of a standalone `@`
  * `return this` instead of `return @`
* Place class properties in the following order:
    * Class methods and properties (methods starting with a `@`)
    * Instance methods and properties
* [Avoid platform-dependent code](https://flight-manual.atom.io/hacking-atom/sections/cross-platform-compatibility/)

### Documentation Styleguide

* Use [Markdown](https://daringfireball.net/projects/markdown).
* Reference methods and classes in markdown with the custom `{}` notation:
    * Reference classes with `{ClassName}`
    * Reference instance methods with `{ClassName::methodName}`
    * Reference class methods with `{ClassName.methodName}`

_This document is based on the [ATOM Contributor Guidelines](https://github.com/atom/atom/blob/master/CONTRIBUTING.md)_
