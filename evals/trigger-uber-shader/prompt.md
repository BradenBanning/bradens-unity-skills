---
name: trigger-uber-shader
tags: [trigger]
runs: 2
max_turns: 4
timeout_seconds: 240
allowed_tools: [Skill, Read, Glob, Grep]
---
Our URP game needs a dissolve effect on enemies when they die, and the selected unit should glow. I was going to write a new shader for each. What's the best way to do it without hurting batching?

Plan how you'd do this - don't run or change anything yet.
