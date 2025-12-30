"""
AI Module with Local Rule-Based and OpenAI LLM Insights.
"""

import os
import random
from datetime import date
from typing import List, Dict, Any, Callable, Optional
from openai import OpenAI

# -------------------------------
# Rule-based fallback insights
# -------------------------------
def default_rule_based_insights(activities: List) -> List[str]:
    if not activities:
        return ["No activities recorded today. Start with one simple task."]

    insights = []

    total_planned = sum(getattr(a, "planned_minutes", 0) for a in activities)
    total_elapsed = sum(a.tick_update() for a in activities) // 60
    completed = [a for a in activities if a.completed]
    pending = [a for a in activities if not a.completed]

    completion_rate = (len(completed) / len(activities) * 100) if activities else 0
    comp_planned = sum(a.planned_minutes for a in completed)
    productivity = (comp_planned / total_planned * 100) if total_planned > 0 else 0

    insights.append(f"Productivity score: {productivity:.1f}%")
    insights.append(f"Completed {len(completed)} of {len(activities)} tasks.")
    insights.append(f"Total time tracked: {total_elapsed} minutes")

    categories = {}
    for a in activities:
        cat = a.category
        categories.setdefault(cat, 0)
        categories[cat] += a.tick_update() // 60

    if categories:
        top = max(categories.keys(), key=lambda x: categories[x])
        insights.append(f"Most productive category: {top} ({categories[top]} minutes)")

    if completion_rate < 40:
        insights.append("Completion rate is low. Try finishing a small task to build momentum.")
    elif completion_rate > 80:
        insights.append("Excellent work! You're maintaining strong consistency today.")

    insights.append(random.choice([
        "Stay consistent and take short breaks.",
        "You're doing well. Maintain your pace.",
        "Consider tackling the highest-priority task next.",
        "Small progress is still progress. Keep going."
    ]))

    return insights

# -------------------------------
# OpenAI LLM-based Insight Model
# -------------------------------
class LLMInsightModel:
    """
    Uses OpenAI GPT models to generate smart insights.
    """
    def __init__(self, model_name="gpt-4o-mini"):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable not set. Please configure it."
            )
        self.client = OpenAI(api_key=api_key)
        self.model = model_name

    def __call__(self, activities: List) -> List[str]:
        """
        When called, generate insights using OpenAI API.
        """
        task_summary = []
        for a in activities:
            task_summary.append({
                "name": a.name,
                "planned_minutes": a.planned_minutes,
                "elapsed_minutes": a.tick_update() // 60,
                "completed": a.completed,
                "category": a.category,
                "priority": a.priority,
                "time_slot": a.activity_time,
                "activity_date": a.activity_date.isoformat() if a.activity_date else None
            })

        prompt = f"""
You are an expert productivity assistant.
Analyze this list of tasks and generate **personalized, practical insights**.

Your response must be a **bullet list** of 5 to 8 clear suggestions.
Profile the user's productivity, time management, category balance, prioritization,
time slot effectiveness, and completion behavior.

Today's date: {date.today().isoformat()}
Task data:
{task_summary}
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You provide actionable productivity insights."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.3
            )
            # FIX: Use attribute access instead of dictionary-style indexing
            result = response.choices[0].message.content
            
            # Parse the response into bullet points
            lines = []
            for line in result.split("\n"):
                line = line.strip()
                if line:
                    # Remove bullet points, dashes, or numbers
                    if line.startswith(("•", "-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")):
                        line = line[1:].strip() if line[0] in "•-*" else line[2:].strip()
                    lines.append(line)
            
            return lines if lines else ["No specific insights generated."]

        except Exception as e:
            return [f"LLM Error: {e}", "Falling back to rule-based insights..."] + default_rule_based_insights(activities)


# -------------------------------
# AI Analyzer
# -------------------------------
class AIAnalyzer:
    def __init__(self, model: Optional[Callable[[List], List[str]]] = None):
        if model:
            self.model = model
        else:
            # Try LLM first
            try:
                self.model = LLMInsightModel()
                print("LLM Insight Model enabled.")
            except RuntimeError as e:
                print(f"LLM unavailable: {e}")
                self.model = default_rule_based_insights
            except Exception as e:
                print(f"Unexpected error initializing LLM: {e}")
                self.model = default_rule_based_insights

    def generate_daily_insights(self, activities: List) -> str:
        try:
            lines = self.model(activities)
            header = f"📊 DAILY INSIGHTS ({date.today().isoformat()})\n" + "="*40
            return "\n".join([header] + lines)
        except Exception as e:
            fallback = default_rule_based_insights(activities)
            return f"Model error: {e}\n\n" + "\n".join(["Fallback insights:"] + fallback)


# -------------------------------
# Weekly and productivity summaries
# -------------------------------
def generate_weekly_report(weekly_data: List[Dict]) -> str:
    if not weekly_data:
        return "No weekly data available."

    productive_days = [d for d in weekly_data if d.get("productivity", 0) > 70]
    avg_prod = sum(d.get("productivity", 0) for d in weekly_data) / len(weekly_data)
    total_time = sum(d.get("total_minutes", 0) for d in weekly_data)

    lines = [
        "📅 WEEKLY SUMMARY",
        "="*40,
        f"Average productivity: {avg_prod:.1f}%",
        f"Total time tracked: {total_time} minutes",
        f"Highly productive days: {len(productive_days)}",
        "",
        "Day-by-day breakdown:"
    ]

    for d in weekly_data:
        icon = "🌟" if d.get("productivity", 0) > 80 else "✨" if d.get("productivity", 0) > 60 else "📝"
        lines.append(f"{icon} {d.get('date', 'N/A')}: {d.get('productivity', 0):.1f}% ({d.get('total_minutes', 0)} min)")

    return "\n".join(lines)

def generate_productivity_insights(activities: List) -> str:
    items = default_rule_based_insights(activities)
    return "PRODUCTIVITY TIPS\n" + "="*40 + "\n" + "\n".join(items)