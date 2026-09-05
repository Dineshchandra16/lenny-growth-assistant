"""
backend/scripts/download_transcripts.py
─────────────────────────────────────────
Fetches or generates structured transcript files for Lenny's Podcast archive.

Creates Markdown files with frontmatter metadata (title, guest, date)
and timestamped transcript sections for ingestion.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

SAMPLE_EPISODES = [
    {
        "filename": "elena_verna_plg.md",
        "title": "Elena Verna on B2B Product-Led Growth and PLG Loops",
        "guest": "Elena Verna",
        "date": "2023-04-12",
        "content": """---
episode_title: "Elena Verna on B2B Product-Led Growth and PLG Loops"
guest_name: "Elena Verna"
publish_date: "2023-04-12"
---

# Elena Verna on B2B Product-Led Growth and PLG Loops

[00:00:15] **Lenny:** Welcome to the podcast. Today I'm speaking with Elena Verna, one of the most respected growth advisors in tech, having advised Miro, Amplitude, MongoDB, and Netlify. Elena, what is the biggest misconception about Product-Led Growth in B2B?

[00:01:20] **Elena Verna:** The biggest misconception is thinking that PLG is just a self-serve checkout or a free trial. PLG is an end-to-end organizational model where the product drives acquisition, retention, and monetization. If your product doesn't naturally create expansion loops where one user invites another or creates content that attracts other users, you don't have PLG—you just have a self-serve payment gateway.

[00:04:45] **Lenny:** How should teams distinguish between Product-Led Growth and Sales-Led Growth?

[00:05:30] **Elena Verna:** In sales-led, the sales rep creates the value proposition before the user touches the software. In product-led, the user experiences value first—what we call the 'Aha moment'—and only then do you introduce sales or monetization as an accelerator, not a gatekeeper. We call this Product-Led Sales (PLS). The product qualifies the lead (PQL), and sales closes enterprise expansion.

[00:09:10] **Lenny:** What is a Product Qualified Lead (PQL) and how do you define the threshold?

[00:10:05] **Elena Verna:** A PQL is a user or workspace that has reached meaningful activation and usage velocity. For Miro, a PQL wasn't someone who created a board; it was a board with at least 3 active collaborators within 7 days. Once a workspace crosses that threshold, their conversion probability jumps 5x. That's when your sales team should reach out.

[00:14:20] **Lenny:** What are the core growth loops every B2B PM should understand?

[00:15:10] **Elena Verna:** There are four primary loops:
1. Viral Invitation Loops: User invites a teammate to collaborate (e.g. Figma, Miro, Slack).
2. Content Loops: User creates public or shared artifacts that rank on search or get shared externally (e.g. Notion templates, Canva designs).
3. Paid Acquisition Loops: Revenue from subscribers directly funds performance marketing with payback under 12 months.
4. Sales Expansion Loops: Land in one department, demonstrate ROI, expand to company-wide enterprise agreement.
""",
    },
    {
        "filename": "brian_balfour_four_fits.md",
        "title": "Brian Balfour on the Four Product-Market Fits",
        "guest": "Brian Balfour",
        "date": "2022-11-15",
        "content": """---
episode_title: "Brian Balfour on the Four Product-Market Fits"
guest_name: "Brian Balfour"
publish_date: "2022-11-15"
---

# Brian Balfour on the Four Product-Market Fits

[00:00:20] **Lenny:** Today my guest is Brian Balfour, founder and CEO of Reforge and former VP of Growth at HubSpot. Brian, you famously argued that Product-Market Fit is not enough. Why is that?

[00:01:10] **Brian Balfour:** Product-Market fit is necessary, but it's only one piece of the puzzle. You cannot build a $100M+ company on Product-Market Fit alone. You need four fits that all fit together like gears in an engine:
1. Market-Product Fit
2. Product-Channel Fit
3. Channel-Model Fit
4. Model-Market Fit

[00:03:40] **Lenny:** Can you break down Product-Channel Fit? Why do so many startups fail here?

[00:04:15] **Brian Balfour:** Products are built to fit channels, not the other way around. You do not control Google's SEO algorithms, Facebook's ad auction, or Apple's App Store. The rules of the channel are set by the platform. If your product requires complex onboarding and 3 weeks of setup, it will never work on paid social where attention spans are 3 seconds. Virality requires low friction; SEO requires high volume of indexable pages.

[00:08:00] **Lenny:** What is Channel-Model Fit?

[00:08:50] **Brian Balfour:** Your monetization model dictates which channels you can afford. If your Average Revenue Per User (ARPU) is $10/year, you cannot use outbound enterprise sales or high-CAC paid search. You are forced into virality or user-generated SEO. Conversely, if your ARPU is $100k/year, virality is rare, and you must build outbound sales and account-based marketing.

[00:12:30] **Lenny:** How does retention tie into all of this?

[00:13:15] **Brian Balfour:** Retention is the bedrock of growth. If your retention curve does not flatten parallel to the x-axis, your bucket is leaky. Acquiring more users into a leaky bucket simply burns capital faster. The best growth teams spend 60% of their time on activation and retention before scaling top-of-funnel acquisition.
""",
    },
    {
        "filename": "sean_ellis_experimentation.md",
        "title": "Sean Ellis on Growth Sprints and High-Velocity Experimentation",
        "guest": "Sean Ellis",
        "date": "2023-01-20",
        "content": """---
episode_title: "Sean Ellis on Growth Sprints and High-Velocity Experimentation"
guest_name: "Sean Ellis"
publish_date: "2023-01-20"
---

# Sean Ellis on Growth Sprints and High-Velocity Experimentation

[00:00:10] **Lenny:** Sean Ellis coined the term 'Growth Hacker' and led early growth at Dropbox, Eventbrite, and LogMeIn. Sean, what separates top-tier growth teams from average ones?

[00:01:05] **Sean Ellis:** Testing velocity. Top growth teams run 20 to 50 experiments per month, whereas average teams run 2 or 3. Growth is a game of probability. If only 25% of your experiments win, running 4 tests gives you 1 win. Running 40 tests gives you 10 compound wins.

[00:04:10] **Lenny:** How do you prioritize experiment ideas without endless debates?

[00:05:00] **Sean Ellis:** We use the ICE scoring framework:
- **Impact:** How much will this move our North Star Metric if it succeeds? (1-10)
- **Confidence:** How certain are we based on qualitative or quantitative data? (1-10)
- **Ease:** How fast can engineering and design ship this test? (1-10)

Score each idea: (Impact + Confidence + Ease) / 3. Then rank your backlog and commit to the top 3-5 tests in every weekly growth sprint.

[00:09:30] **Lenny:** What is the 'Must-Have' survey for measuring Product-Market Fit?

[00:10:15] **Sean Ellis:** Ask your active users: 'How would you feel if you could no longer use this product?'
Options:
1. Very disappointed
2. Somewhat disappointed
3. Not disappointed

If 40% or more respond 'Very disappointed', you have achieved Product-Market Fit. If you are below 40%, stop scaling marketing and focus entirely on core product value and user segment refinement.
""",
    },
    {
        "filename": "casey_winters_retention_loops.md",
        "title": "Casey Winters on Retention, Engagement Loops, and Pricing Strategy",
        "guest": "Casey Winters",
        "date": "2023-07-05",
        "content": """---
episode_title: "Casey Winters on Retention, Engagement Loops, and Pricing Strategy"
guest_name: "Casey Winters"
publish_date: "2023-07-05"
---

# Casey Winters on Retention, Engagement Loops, and Pricing Strategy

[00:00:15] **Lenny:** Today I'm joined by Casey Winters, former Chief Product Officer at Eventbrite and Growth Lead at Pinterest and Grubhub. Casey, how do you diagnose whether a growth problem is actually an onboarding problem?

[00:01:25] **Casey Winters:** When teams see low Day 30 retention, they usually try to fix it with re-engagement emails or push notifications at Day 25. That almost never works. Day 30 retention is determined in the first 10 minutes of usage. If the user doesn't complete the core setup and experience the core value immediately, they will churn.

[00:06:10] **Lenny:** What are the characteristics of an effective growth loop?

[00:07:00] **Casey Winters:** A loop has three steps:
1. Input: A new cohort of users or actions.
2. Action: Users generate content, invite others, or supply data.
3. Output: That action naturally attracts the next cohort of users.

At Pinterest, a user saves a pin (action). That pin is indexed by Google (distribution). A new user searching on Google clicks the pin and signs up (input). The loop is self-reinforcing.

[00:11:40] **Lenny:** What advice do you give on SaaS pricing and packaging?

[00:12:30] **Casey Winters:** Align your value metric with customer success. Charge based on what grows when the customer gets more value—whether that's active users, events tracked, or revenue processed. Never charge for features that drive adoption, like team member seats if collaboration is your core retention driver.
""",
    },
]


def download_or_create_transcripts(output_dir: Path) -> list[Path]:
    """Write sample transcript files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created_files: list[Path] = []

    for ep in SAMPLE_EPISODES:
        file_path = output_dir / ep["filename"]
        file_path.write_text(ep["content"], encoding="utf-8")
        created_files.append(file_path)
        print(f"Created transcript: {file_path.name}")

    return created_files


def main():
    parser = argparse.ArgumentParser(description="Download / scaffold Lenny transcript archive")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("transcripts"),
        help="Directory to save transcript markdown files",
    )
    args = parser.parse_args()
    files = download_or_create_transcripts(args.output_dir)
    print(f"\nSaved {len(files)} transcript files in {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
