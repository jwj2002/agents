*[artifact]: A markdown report produced by an agent, stored in .agents/outputs/
*[CLI]: Command-Line Interface
*[CONTRACT]: Agent that defines the API boundary between backend and frontend
*[CONTRACT-lite]: Inline contract section used for simple fullstack changes instead of the full CONTRACT agent
*[DLP]: Data Loss Prevention
*[ENUM_VALUE]: A failure pattern where frontend uses Python enum name instead of the stored value string
*[HACCP]: Hazard Analysis Critical Control Points — food safety management system
*[LSP]: Language Server Protocol — provides real-time code intelligence (errors, completions)
*[MAP]: Agent that investigates the codebase for complex issues
*[MAP-PLAN]: Agent that investigates and creates an implementation plan in a single phase
*[MCP]: Model Context Protocol — standard for connecting AI tools to external data sources
*[PATCH]: The only agent that modifies code — implements changes per the plan
*[pipeline]: The sequence of agents that process a GitHub issue from investigation to verification
*[pipeline tier]: The agent sequence used inside orchestrate (TRIVIAL, SIMPLE, or COMPLEX)
*[PLAN-CHECK]: Agent that validates a plan's completeness before implementation begins
*[PROVE]: Agent that verifies implementation correctness and records outcomes
*[PROVE-lite]: Reduced verification for trivial issues — runs only basic gates
*[routing tier]: The complexity classification that determines which workflow to use
*[SSPR]: Self-Service Password Reset
*[worktree]: An isolated copy of a git repository for parallel development work
