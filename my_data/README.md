# 🧠 Personal Knowledge Base

This folder (`my_data/`) is your AI's personal memory bank. The Interview Helper application will automatically read **every `.txt` and `.md` file** in this folder before answering a question. 

By adding files here, you guarantee that the AI uses your exact resume, projects, and experiences to generate answers for behavioral and non-technical interview questions.

## How to Add Knowledge

1. **Create a File:** Create a new `.txt` or `.md` file in this folder.
2. **Add Your Content:** Paste in any relevant information you want the AI to know.
3. **That's It!** You do not need to restart the application. The AI reads this folder fresh every single time you ask a question.

## What Should I Put Here?

- **Your Resume:** We already have `profile.md` for this. Keep it updated with your latest experience.
- **Project Deep-Dives:** Create a file like `project_hrdocu.md` and dump all your architecture decisions, challenges faced, and metrics achieved for that specific project.
- **Job Descriptions:** Are you interviewing for a specific role? Copy/paste the job description into a file like `target_job.txt`. The AI will tailor your experience to match those exact requirements!
- **Behavioral STAR Stories:** Write down raw notes about a time you failed, or a time you resolved a conflict (`star_stories.txt`). The AI will polish them into perfect spoken answers when asked.

## ⚠️ Important Rules

1. **Only text files:** The app currently only reads files ending in `.md` or `.txt`. Do not put PDFs, Word documents, or images in here.
2. **Keep it concise:** Llama 3.2 is fast, but if you drop a 1,000-page book in here, it will slow down and might hit its context limit. Stick to your resume, cover letters, and project notes (ideally under 15-20 pages total).
3. **File organization:** You can put files in subfolders inside `my_data/` if you want! The application will still find and read them automatically.
