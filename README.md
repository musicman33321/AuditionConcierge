# AuditionConcierge🎭 Disney Audition Search Agent
A Height-Aware, Performer-Focused Multi-Agent System for Audition Discovery

Track: Concierge Agents

## 1. Overview

Disney auditions often include strict height ranges, performer-presentation requirements, and union classifications — yet the official audition system does not allow performers to filter by any of these critical attributes. Searching for opportunities becomes a time-consuming, frustrating process: reading through pages of text, converting heights, interpreting inconsistent formats, and hoping not to miss a role.

This project builds a Concierge-style, multi-agent audition search assistant that automatically fetches the Disney audition feed, preprocesses and structures the data, and lets performers ask nuanced questions such as:

“I’m a 5'4" female-presenting dancer — what auditions are open for me?”

“Show Equity roles requiring 5’2”–5’6” height.”

“Are there any character performer auditions for my height this month?”

The system uses agent orchestration, custom tools, context-aware preprocessing, and Gemini models to make audition discovery fast, accurate, and performer-centric.

## 2. Problem

The Disney audition feed is not built for performers searching by their own attributes. The limitations include:

No built-in filtering by height, even though most roles require strict ranges

No filtering by male/female-presenting performer classifications

No easy way to check for Equity vs. Non-Equity roles

Height formats are inconsistent (e.g., “5’4”, “64 in”, “162 cm”)

All listings must be manually scanned

Semantic understanding (e.g., “dancer who fits 5’3–5’5 guidelines”) doesn’t exist

Performers lose time, miss opportunities, and often struggle to identify roles they are eligible for.

This project aims to solve all of those pain points.

## 3. Solution

The Disney Audition Search Agent converts the raw audition feed into a structured representation that supports both semantic and attribute-based queries. The agent:

Fetches the latest auditions
Using custom tools to retrieve and sanitize the XML/HTML feed.

Preprocesses and normalizes the data

Extracts height ranges

Converts heights (feet/inches ↔ centimeters)

Identifies performer-presentation

Detects Equity vs. Non-Equity

Supports flexible user input

Open-ended semantic queries powered by Gemini

Returns customized audition recommendations
Clean, concise, performer-specific results.

## 4. Architecture

The system uses a sequential multi-agent pipeline designed for clarity, separation of concerns, and context efficiency.

1. Locale Agent

Detects user locale, region, and preferred height units

Ensures height conversions align with user expectations

Exposed to other agents via AgentTool (A2A protocol)

2. Data Agent

Retrieves audition feed

Performs full HTML/XML cleanup

Extracts height ranges, role details, and relevant metadata

Normalizes heights into consistent units

Converts the cleaned result into a structured dataframe

This preprocessing happens before any LLM involvement, minimizing token usage and context size.

3. Summarizer / Query Agent

Interprets user questions (semantic + structured)

Applies all filters, including:

height

performer presentation

role type

Equity status

Returns a concise answer, not raw text dumps

Tools

fetch_disney_auditions — custom tool for feed retrieval

clean_html / XML parser — strips noise and extracts fields

convert_length — robust height conversion utility

google_search — background augmentation for ambiguous terms


## 5. How to Run

Clone the repository

git clone https://github.com/musicman33321/AuditionConcierge.git
cd AuditionConcierge


Install dependencies

pip install -r requirements.txt


Launch the notebook

jupyter notebook disneyauditionsearch.ipynb


Run the notebook cells from top to bottom

The data preprocessing step runs automatically (fetching the latest Disney audition feed and cleaning it).

Once the preprocessing completes, you can submit queries using the provided UI elements or by calling the agent directly.

Example queries

“I’m a 5'4" female-presenting dancer — what auditions are open for me?”

“Show me Equity roles between 5'2" and 5'6".”

“List any character performer auditions available this month.”

