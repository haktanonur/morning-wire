# 2. Python Instead of Java

## Status
Accepted

## Context
The project owner's day job is Java/Spring Boot. This project, however, is a "fetch data -> transform -> call an external service" glue-code job.

## Decision
Python 3.12 is used. Rationale: libraries like yfinance exist ready-made, less boilerplate, faster Lambda cold starts, and this kind of scripting/data-pipeline job is conventionally Python/Node/Go in the industry.

## Consequences
A small learning-curve cost for the project owner (less daily fluency than Java), offset by faster overall development speed and easier maintenance for this kind of task.
