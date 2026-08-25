using System;

[Serializable]
public class LearnerStateModel
{
    // =====================================================
    // Human Digital Twin State (0.0 to 1.0 Scale)
    // Values are normalized between 0.0 (lowest) and 1.0 (highest).
    // =====================================================
    public float knowledge = 0.5f;
    public float confidence = 0.5f;
    public float engagement = 0.5f;
    public float hintDependency = 0.5f;

    // =====================================================
    // Interaction Statistics for Thesis Analysis
    // =====================================================
    public int questionsAnswered = 0;
    public int correctAnswers = 0;
    public int incorrectAnswers = 0;
    public float averageResponseTime = 0f;

    // =====================================================
    // Lesson Progress & Scenario Context
    // =====================================================
    public string currentLesson = "Café-Szenario";
    public string currentDifficulty = "Beginner";

    // =====================================================
    // Reset State
    // =====================================================
    public void Reset()
    {
        knowledge = 0.5f;
        confidence = 0.5f;
        engagement = 0.5f;
        hintDependency = 0.5f;

        questionsAnswered = 0;
        correctAnswers = 0;
        incorrectAnswers = 0;

        averageResponseTime = 0f;

        currentLesson = "Café-Szenario";
        currentDifficulty = "Beginner";
    }

    // =====================================================
    // Interaction Statistics Modifiers
    // =====================================================
    public void RecordCorrectAnswer()
    {
        questionsAnswered++;
        correctAnswers++;
    }

    public void RecordIncorrectAnswer()
    {
        questionsAnswered++;
        incorrectAnswers++;
    }

    public void UpdateAverageResponseTime(float latency)
    {
        if (questionsAnswered <= 1)
        {
        averageResponseTime = latency;
        }
        else
        {
            averageResponseTime =
            ((averageResponseTime * (questionsAnswered - 1)) + latency)
            / questionsAnswered;
            }
            }

    // =====================================================
    // Human Digital Twin State Setters
    // =====================================================
    public void SetKnowledge(float value)
    {
        knowledge = Clamp01(value);
    }

    public void SetConfidence(float value)
    {
        confidence = Clamp01(value);
    }

    public void SetEngagement(float value)
    {
        engagement = Clamp01(value);
    }

    public void SetHintDependency(float value)
    {
        hintDependency = Clamp01(value);
    }

    // =====================================================
    // Utility Bounds Protection
    // =====================================================
    private float Clamp01(float value)
    {
        if (value < 0f) return 0f;
        if (value > 1f) return 1f;
        return value;
    }
}