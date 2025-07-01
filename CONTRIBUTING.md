# Contributing to Serena

Serena is under active development. We are just discovering what it can do and where the limitations lie.

Feel free to share your learnings by opening open new issues, feature requests and extensions.

## Developer Environment Setup

You can have a local setup via `uv` or a docker interpreter-based setup. 
The repository is also configured to seamlessly work within a GitHub Codespace. See the instructions
for the various setup scenarios below.

Independently of how the setup was done, the virtual environment can be 
created and activated via `uv` (see below), and the various tasks like formatting, testing, and documentation building
can be executed using `poe`. For example, `poe format` will format the code, including the 
notebooks. Just run `poe` to see the available commands.

### Python (uv) setup

You can install a virtual environment with the required as follows

1. Create a new virtual environment: `uv venv`
2. Activate the environment:
    * On Linux/Unix/macOS: `source .venv/bin/activate`
    * On Windows: `.venv\Scripts\activate.bat` (in cmd/ps) or `source .venv/Scripts/activate` (in git-bash) 
3. Install the required packages with all extras: `uv pip install --all-extras -r pyproject.toml -e .`

### Docker setup

Build the docker image with

```shell
docker build -t serena .
```

and run it with the repository mounted as a volume:

```shell
docker run -it --rm -v "$(pwd)":/workspace serena
```

You can also just run `bash docker_build_and_run.sh`, which will do both things
for you.

Note: For the Windows subsystem for Linux (WSL), you may need to adjust the path for the
volume.

## Running Tools Locally

The Serena tools (and in fact all Serena code) can be executed without an LLM, and also without
any MCP specifics (though you can use the mcp inspector, if you want).

An example script for running tools is provided in [scripts/demo_run_tools.py](scripts/demo_run_tools.py).

## Adding a New Supported Language

Serena interacts with code through language servers which are included in
the `solidlsp` package. It is rather easy to include a new supported language
if an LSP implementation for it exists. You just need to:

1. create a new subclass of `SolidLanguageServer`
2. add a new value to the `Language` enum
3. make a new `elif` case in the `SolidLanguageServer.create` method
4. add a test repo of the new language to `test/resources/repos/<new_language>/test_repo`
   and new tests in `test/solidlsp/<new_language>`. Similar to existing tests for other languages
5. also add a new case to the parameterized tests in `test/serena/test_serena_agent`

The subclasses are typically easy to write, have a look at the 
[PyrightLanguageServer](src/multilspy/language_servers/pyright_language_server/pyright_server.py) 
for an example, or at any other implementation to see how non-python
dependencies for language servers are handled there.
There are also some tips from the multilspy admin [here](https://github.com/microsoft/multilspy/issues/5).
