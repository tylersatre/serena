# Latest

Status of the `main` branch. Changes prior to the next official version change will appear here.

* **Reduce the use of asyncio to a minimum**, improving stability and reducing the need for workarounds
   * Switch to newly developed fully synchronous LSP library `solidlsp` (derived from `multilspy`),
     removing our fork of `multilspy` (src/multilspy)
   * Switch from fastapi (which uses asyncio) to Flask in the Serena dashboard
   * The MCP server is the only asyncio-based component now, which resolves cross-component loop contamination,
     such that process isolation is no longer required.
     Neither are non-graceful shutdowns on Windows.
* **Improved editing tools**: The editing logic was simplified and improved, making it more robust.
   * The "minimal indentation" logic was removed, because LLMs did not understand it.
   * The logic for the insertion of empty lines was improved (mostly controlled by the LLM now)
* Add a task queue for the agent, which is executed in a separate and thread and
   * allows the language server to be initialized in the background, making the MCP server respond to requests
     immediately upon startup,
   * ensures that all tool executions are fully synchronized (executed linearly).
* `SearchForPatternTool`: Better default, extended parameters and description for restricting the search
* Language support:
   * Better support for C# by switching from `omnisharp` to Microsoft's official C# language server.
   * **Add support for Clojure**
* Configuration:
   * Add option `web_dashboard_open_on_launch` (allowing the dashboard to be enabled without opening a browser window) 

Fixes:
* Fix `ExecuteShellCommandTool` and `GetCurrentConfigTool` hanging on Windows
* Fix project activation by name via `--project` not working (was broken in previous release) 
* Improve handling of indentation and newlines in symbolic editing tools
* Fix `InsertAfterSymbolTool` failing for insertions at the end of a file that did not end with a newline
* Fix `InsertBeforeSymbolTool` inserting in the wrong place in the absence of empty lines above the reference symbol
* Fix `ReplaceSymbolBodyTool` changing whitespace before/after the symbol
* Fix repository indexing not following links and catch exceptions during indexing, allowing indexing
  to continue even if unexpected errors occur for individual files.
* Fix `ImportError` in Ruby language server.
* Fix some issues with gitignore matching and interpreting of regexes in `search_for_pattern` tool.

# 2025-06-20

* **Overhaul and major improvement of editing tools!**
  This represents a very important change in Serena. Symbols can now be addressed by their `name_path` (including nested ones)
  and we introduced a regex-based replaced tools. We tuned the prompts and tested the new editing mechanism.
  It is much more reliable, flexible, and at the same time uses fewer tokens.
  The line-replacement tools are disabled by default and deprecated, we will likely remove them soon.
* **Better multi-project support and zero-config setup**: We significantly simplified the config setup, you no longer need to manually
  create `project.yaml` for each project. Project activation is now always available. 
  Any project can now be activated by just asking the LLM to do so and passing the path to a repo.
* Dashboard as web app and possibility to shut down Serena from it (or the old log GUI).
* Possibility to index your project beforehand, accelerating Serena's tools.
* Initial prompt for project supported (has to be added manually for the moment)
* Massive performance improvement of pattern search tool
* Use **process isolation** to fix stability issues and deadlocks (see #170). 
  This uses separate process for the MCP server, the Serena agent and the dashboard in order to fix asyncio-related issues.

# 2025-05-24

* Important new feature: **configurability of mode and context**, allowing better integration in a variety of clients.
  See corresponding section in readme - Serena can now be integrated in IDE assistants in a more productive way. 
  You can now also do things like switching to one-shot planning mode, ask to plan something (which will create a memory),
  then switch to interactive editing mode in the next conversation and work through the plan read from the memory.
* Some improvements to prompts.

# 2025-05-21

**Significant improvement in symbol finding!**

* Serena core:
    * `FindSymbolTool` now can look for symbols by specifying paths to them, not just the symbol name
* Language Servers:
    * Fixed `gopls` initialization
    * Symbols retrieved through the symbol tree or through overview methods now are linked to their parents


# 2025-05-19

* Serena core:
    * Bugfix in `FindSymbolTool` (a bug fixed in LS)
    * Fix in `ListDirTool`: Do not ignore files with extensions not understood by the language server, only skip ignored directories
      (error introduced in previous version)
    * Merged the two overview tools (for directories and files) into a single one: `GetSymbolsOverviewTool`
    * One-click setup for Cline enabled
    * `SearchForPatternTool` can now (optionally) search in the entire project
    * New tool `RestartLanguageServerTool` for restarting the language server (in case of other sources of editing apart from Serena)
    * Fix `CheckOnboardingPerformedTool`:
        * Tool description was incompatible with project change
        * Returned result was not as useful as it could be (now added list of memories)

* Language Servers:
    * Add further file extensions considered by the language servers for Python (.pyi), JavaScript (.jsx) and TypeScript (.tsx, .jsx)
    * Updated multilspy, adding support for Kotlin, Dart and C/C++ and several improvements.
    * Added support for PHP
    

# 2025-04-07

> **Breaking Config Changes**: make sure to set `ignore_all_files_in_gitignore`, remove `ignore_dirs`
>  and (optionally) set `ignore_paths` in your project configs. See [updated config template](myproject.template.yml)

* Serena core:
    * New tool: FindReferencingCodeSnippets
    * Adjusted prompt in CreateTextFileTool to prevent writing partial content (see [here](https://www.reddit.com/r/ClaudeAI/comments/1jpavtm/comment/mloek1x/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button)).
    * FindSymbolTool: allow passing a file for restricting search, not just a directory (Gemini was too dumb to pass directories)
    * Native support for gitignore files for configuring files to be ignored by serena. See also
      in *Language Servers* section below.
    * **Major Feature**: Allow Serena to switch between projects (project activation)
        * Add central Serena configuration in `serena_config.yml`, which 
            * contains the list of available projects
            * allows to configure whether project activation is enabled
            * now contains the GUI logging configuration (project configurations no longer do)
        * Add new tools `activate_project` and `get_active_project`
        * Providing a project configuration file in the launch parameters is now optional
* Logging:
    * Improve error reporting in case of initialization failure: 
      open a new GUI log window showing the error or ensure that the existing log window remains visible for some time
* Language Servers:
    * Fix C# language server initialization issue when the project path contains spaces
    * Native support for gitignore in overview, document-tree and find_references operations.
      This is an **important** addition, since previously things like `venv` and `node_modules` were scanned
      and were likely responsible for slowness of tools and even server crashes (presumably due to OOM errors).
* Agno: 
    * Fix Agno reloading mechanism causing failures when initializing the sqlite memory database #8
    * Fix Serena GUI log window not capturing logs after initialization

# 2025-04-01

Initial public version
