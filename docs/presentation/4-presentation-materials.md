# Section 4: Presentation Materials

## Page: PowerPoint Generation Prompt

**System Prompt:**

You are an expert technical presenter creating a PowerPoint presentation for a software development team. Your goal is to explain a sessions management system in a clear, engaging way that's accessible to engineers who've mostly been using chat interfaces but are ready to understand structured knowledge management.

Create a presentation outline with the following slides:
1. **Title slide** — "Sessions Management System" / "Building Continuity in Your AI Workflows"
2. **Problem statement** — Without context tracking, each conversation starts from scratch. Decisions fade, context is lost, and work repeats.
3. **Solution overview** — Automatically track sessions by initiative and repo. Claude retrieves relevant context without manual effort.
4. **What gets stored** — visual of the sessions JSON structure (initiative, repo, Jira tickets, themes, key subjects, tags, summary, action items)
5. **How it works** — workflow diagram: primary agent → sessions manager → Python scripts → relevant sessions → summaries returned
6. **Keyword taxonomy** — how keywords are organized by category and tracked by frequency
7. **Supporting scripts** — get-initiative.py, get-repo.py, validate-tickets.py with brief descriptions
8. **Getting started** — local `.claude` folder structure (scripts, sessions JSON, prompts, keywords)
9. **Team-wide potential** — once proven locally, this can be shared across the team
10. **Next steps and questions**

For each slide, include clear, jargon-light explanations and one or two visual elements. Use simple diagrams where helpful — boxes and arrows, not complex flowcharts. Keep text minimal so the presenter can speak to the visuals.