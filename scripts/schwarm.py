from crewai import Agent, Crew, Process, Task
from langchain_openai import ChatOpenAI

# 1. Verbindung zu deinem lokalen LM Studio aufbauen
local_llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model_name="qwen2.5-72b-instruct"
)

# 2. Agent definieren (Rolle & Ziel)
recherche_agent = Agent(
    role="Chef-Analyst",
    goal="Erstelle präzise Analysen für das System.",
    backstory="Du bist ein erfahrener IT-Systemarchitekt.",
    verbose=True,
    llm=local_llm
)

# 3. Aufgabe definieren
aufgabe = Task(
    description="Erkläre in genau 2 Sätzen, warum lokale KI auf dem Mac Studio M3 Ultra genial ist.",
    expected_output="Zwei präzise Sätze auf Deutsch.",
    agent=recherche_agent
)

# 4. Schwarm starten
schwarm = Crew(
    agents=[recherche_agent],
    tasks=[aufgabe],
    process=Process.sequential
)

ergebnis = schwarm.kickoff()
print("\n--- ERGEBNIS ---")
print(ergebnis)