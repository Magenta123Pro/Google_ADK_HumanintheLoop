# Agent Skills

The Peri-Meter AI project uses custom AI agent skills to handle specialized tasks.

## 1. Hormonal Balance Motivator (`hormonal-balance-motivator`)
**Location:** `.agents/skills/hormonal-balance-motivator/SKILL.md`
**Description:** A specialized agent workflow using `pydantic_ai` to calculate daily hormonal balance scores based on user activities. 
- It uses custom scoring rules for six key hormones (Estrogen, Progesterone, Insulin, Cortisol, LH & FSH, Melatonin).
- It generates empathetic, lighthearted "Girl Talk" and jokes tailored to perimenopausal women.
- It integrates a Human-in-the-Loop (HITL) step where a human Health Coach must intervene and provide an encouraging note if the daily score falls below 50.
