using UnityEngine;

public class TutorAdaptationEngine : MonoBehaviour
{
    [Header("Human Digital Twin State")]
    public LearnerStateModel learnerState = new LearnerStateModel();

    [Header("Local Adaptation Cues (Sent to Flask)")]
    public bool giveHint = false;
    public bool encourage = false;
    public bool simplifyExplanation = false;
    public bool increaseDifficulty = false;

    [Header("Active Animation Style (Enforced by Backend)")]
    [Range(0, 3)]
    public int talkStyle = 0;

    // ==================================================
    // Interface used by TutorChatManager
    // ==================================================
    public LearnerStateModel GetLearnerState()
    {
        return learnerState;
    }

    // ==================================================
    // Update learner state from interaction / response latency
    // ==================================================
    public void UpdateResponseLatency(float latency)
    {
        learnerState.UpdateAverageResponseTime(latency);

        // Engagement heuristic based on response speed
        if (latency <= 5f)
            learnerState.engagement += 0.05f;
        else if (latency >= 15f)
            learnerState.engagement -= 0.05f;

        learnerState.engagement = Mathf.Clamp01(learnerState.engagement);

        EvaluateTutorBehaviour();
    }

    public void RecordCorrectAnswer(bool usedHint)
    {
        learnerState.RecordCorrectAnswer();

        learnerState.knowledge = Mathf.Clamp01(learnerState.knowledge + 0.05f);

        if (usedHint)
        {
            learnerState.confidence = Mathf.Clamp01(learnerState.confidence + 0.02f);
        }
        else
        {
            learnerState.confidence = Mathf.Clamp01(learnerState.confidence + 0.05f);
            learnerState.hintDependency = Mathf.Clamp01(learnerState.hintDependency - 0.03f);
        }

        EvaluateTutorBehaviour();
    }

    public void RecordIncorrectAnswer()
    {
        learnerState.RecordIncorrectAnswer();

        learnerState.knowledge = Mathf.Clamp01(learnerState.knowledge - 0.02f);
        learnerState.confidence = Mathf.Clamp01(learnerState.confidence - 0.05f);

        EvaluateTutorBehaviour();
    }

    public void RecordHintRequest()
    {
        learnerState.hintDependency = Mathf.Clamp01(learnerState.hintDependency + 0.05f);
        EvaluateTutorBehaviour();
    }

    // ==================================================
    // Flask Evaluation Integration
    // ==================================================
    public void UpdateConfidenceFromTutor(string confidenceDetected)
    {
        if (string.IsNullOrEmpty(confidenceDetected)) return;

        string lowerConfidence = confidenceDetected.ToLower();
        if (lowerConfidence == "low")
        {
            learnerState.confidence = Mathf.Clamp01(learnerState.confidence - 0.03f);
        }
        else if (lowerConfidence == "high")
        {
            learnerState.confidence = Mathf.Clamp01(learnerState.confidence + 0.03f);
        }

        EvaluateTutorBehaviour();
    }

    public void UpdateReasonFromTutor(string reason)
    {
        if (string.IsNullOrEmpty(reason)) return;

        string lowerReason = reason.ToLower();
        if (lowerReason == "grammar" || lowerReason == "vocabulary")
        {
            learnerState.knowledge = Mathf.Clamp01(learnerState.knowledge - 0.02f);
        }
        else if (lowerReason == "hesitation")
        {
            learnerState.engagement = Mathf.Clamp01(learnerState.engagement - 0.02f);
        }

        EvaluateTutorBehaviour();
    }

    /// <summary>
    /// Syncs local talkStyle with the strategy enforced by Flask via response headers.
    /// </summary>
    public void SyncTalkStyleFromBackend(int backendTalkStyle)
    {
        talkStyle = Mathf.Clamp(backendTalkStyle, 0, 3);
    }

    // ==================================================
    // Adaptation Policy Engine (Generates Cues for Flask)
    // ==================================================
    private void EvaluateTutorBehaviour()
    {
        giveHint = false;
        encourage = false;
        simplifyExplanation = false;
        increaseDifficulty = false;

        // Low knowledge threshold
        if (learnerState.knowledge < 0.40f)
        {
            simplifyExplanation = true;
        }

        // Low confidence threshold
        if (learnerState.confidence < 0.40f)
        {
            encourage = true;
        }

        // High hint dependency threshold
        if (learnerState.hintDependency > 0.70f)
        {
            giveHint = true;
            simplifyExplanation = true;
        }

        // Strong learner threshold
        if (learnerState.knowledge > 0.80f && learnerState.confidence > 0.80f)
        {
            increaseDifficulty = true;
        }
    }

    public int GetTalkStyle()
    {
        return talkStyle;
    }

    public bool ShouldGiveHint()
    {
        return giveHint;
    }

    public bool ShouldEncourage()
    {
        return encourage;
    }

    public bool ShouldSimplifyExplanation()
    {
        return simplifyExplanation;
    }

    public bool ShouldIncreaseDifficulty()
    {
        return increaseDifficulty;
    }

    public void ResetLearnerState()
    {
        learnerState.Reset();

        talkStyle = 0;
        giveHint = false;
        encourage = false;
        simplifyExplanation = false;
        increaseDifficulty = false;
    }
}