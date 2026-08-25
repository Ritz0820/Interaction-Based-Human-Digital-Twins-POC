using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System.Collections;
using System.Text;
using UnityEngine.Networking;

public class TutorChatManager : MonoBehaviour
{
    [Header("Backend Settings")]
    public string backendUrl = "http://127.0.0.1:5001/turn";

    [Header("Audio & Animation")]
    public AudioSource audioSource;
    public Animator tutorAnimator;

    [Header("Human Digital Twin")]
    public TutorAdaptationEngine adaptationEngine;

    [Header("UI Elements")]
    public TMP_InputField chatInputField;
    public Button sendButton;
    public ScrollRect chatScrollRect;

    [Header("Chat Bubbles")]
    public Transform chatContentContainer;
    public GameObject userBubblePrefab;
    public GameObject tutorBubblePrefab;

    private float timeLastBotMessage;
    private int conversationTurn = 0;

    [System.Serializable]
    private class TurnPayload
    {
        public string user_text;
        public float response_latency;
        public int conversation_turn;

        // Human Digital Twin Metrics
        public float knowledge;
        public float confidence;
        public float engagement;
        public float hint_dependency;

        // Local Adaptation Cues
        public int talk_style;
        public bool give_hint;
        public bool encourage;
        public bool simplify_explanation;
        public bool increase_difficulty;
    }

    void Start()
    {
        if (tutorAnimator != null)
        {
            tutorAnimator.SetBool("isTalking", false);
            tutorAnimator.SetInteger("talkStyle", 0);
        }

        if (sendButton != null)
            sendButton.onClick.AddListener(OnSendButtonClicked);

        // Quality of Life: Press Enter in InputField to send
        if (chatInputField != null)
            chatInputField.onSubmit.AddListener(delegate { OnSendButtonClicked(); });

        timeLastBotMessage = Time.time;
    }

    private void OnSendButtonClicked()
    {
        string text = chatInputField.text;

        if (string.IsNullOrWhiteSpace(text))
            return;

        float latency = Time.time - timeLastBotMessage;

        if (adaptationEngine != null)
            adaptationEngine.UpdateResponseLatency(latency);

        SpawnChatBubble(text, userBubblePrefab);

        chatInputField.text = "";
        chatInputField.ActivateInputField(); // Refocus input field after sending
        sendButton.interactable = false;

        SendUserTurn(text, latency);
    }

    public void SendUserTurn(string userText, float latency)
    {
        StartCoroutine(PostTurnCoroutine(userText, latency));
    }

    private IEnumerator PostTurnCoroutine(string userText, float latency)
    {
        TurnPayload payload = new TurnPayload();

        payload.user_text = userText;
        payload.response_latency = latency;
        payload.conversation_turn = conversationTurn;

        if (adaptationEngine != null)
        {
            LearnerStateModel learner = adaptationEngine.GetLearnerState();

            payload.knowledge = learner.knowledge;
            payload.confidence = learner.confidence;
            payload.engagement = learner.engagement;
            payload.hint_dependency = learner.hintDependency;

            payload.talk_style = adaptationEngine.GetTalkStyle();
            payload.give_hint = adaptationEngine.ShouldGiveHint();
            payload.encourage = adaptationEngine.ShouldEncourage();
            payload.simplify_explanation = adaptationEngine.ShouldSimplifyExplanation();
            payload.increase_difficulty = adaptationEngine.ShouldIncreaseDifficulty();
        }

        string json = JsonUtility.ToJson(payload);

        using (UnityWebRequest request = new UnityWebRequest(backendUrl, "POST"))
        {
            byte[] bodyRaw = Encoding.UTF8.GetBytes(json);

            request.uploadHandler = new UploadHandlerRaw(bodyRaw);
            request.downloadHandler = new DownloadHandlerAudioClip(backendUrl, AudioType.MPEG);
            request.SetRequestHeader("Content-Type", "application/json");

            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError("Backend Error: " + request.error);

                SpawnChatBubble("<i>Backend Error: Could not connect to Greta.</i>", tutorBubblePrefab);
                sendButton.interactable = true;

                yield break;
            }

            // 1. Un-escape response text safely (Null-safe check)
            string rawReply = request.GetResponseHeader("X-Tutor-Reply");
            string tutorReply = string.IsNullOrEmpty(rawReply)
                ? "[Audio message received]"
                : UnityWebRequest.UnEscapeURL(rawReply);

            // 2. Read strategy and evaluation headers from Flask
            string phaseHeader = request.GetResponseHeader("X-Phase");
            string correctHeader = request.GetResponseHeader("X-Correct");
            string hintHeader = request.GetResponseHeader("X-HintRequested");
            string confidenceHeader = request.GetResponseHeader("X-ConfidenceDetected");
            string reasonHeader = request.GetResponseHeader("X-Reason");
            string talkStyleHeader = request.GetResponseHeader("X-Talk-Style");

            bool isAdaptive = (phaseHeader == "ADAPTIVE");
            bool isCorrect = bool.TryParse(correctHeader, out bool c) && c;
            bool hintRequested = bool.TryParse(hintHeader, out bool h) && h;
            int.TryParse(talkStyleHeader, out int enforcedTalkStyle);

            // 3. Feed evaluation data back into Digital Twin adaptation engine
            if (adaptationEngine != null && conversationTurn > 0)
            {
                if (hintRequested)
                {
                    adaptationEngine.RecordHintRequest();
                }

                if (isCorrect)
                {
                    adaptationEngine.RecordCorrectAnswer(hintRequested);
                }
                else
                {
                    adaptationEngine.RecordIncorrectAnswer();
                }
            }

            if (adaptationEngine != null)
            {
                adaptationEngine.UpdateConfidenceFromTutor(confidenceHeader);
                adaptationEngine.UpdateReasonFromTutor(reasonHeader);
                adaptationEngine.SyncTalkStyleFromBackend(enforcedTalkStyle);
            }

            // 4. Spawn chat bubble & play audio/animation using Flask-enforced talk style
            SpawnChatBubble(tutorReply, tutorBubblePrefab);

            AudioClip clip = DownloadHandlerAudioClip.GetContent(request);

            if (clip != null && audioSource != null && clip.length > 0)
            {
                audioSource.clip = clip;
                audioSource.Play();

                StartCoroutine(HandleTalkingAnimation(clip.length, enforcedTalkStyle));
            }
            if (!isAdaptive || isCorrect)
            {
                conversationTurn++;
            }
            timeLastBotMessage = Time.time;
            sendButton.interactable = true;
        }
    }

    private IEnumerator HandleTalkingAnimation(float clipLength, int talkStyle)
    {
        if (tutorAnimator == null)
            yield break;

        tutorAnimator.SetInteger("talkStyle", talkStyle);
        tutorAnimator.SetBool("isTalking", true);

        yield return new WaitForSeconds(clipLength);

        tutorAnimator.SetBool("isTalking", false);
    }

    private void SpawnChatBubble(string message, GameObject prefab)
    {
        if (prefab == null || chatContentContainer == null)
            return;

        GameObject bubble = Instantiate(prefab, chatContentContainer);

        TextMeshProUGUI text = bubble.GetComponentInChildren<TextMeshProUGUI>();

        if (text != null)
            text.text = message;

        // Auto-scroll chat view to bottom
        StartCoroutine(ScrollToBottom());
    }

    private IEnumerator ScrollToBottom()
    {
        yield return new WaitForEndOfFrame();
        Canvas.ForceUpdateCanvases();

        if (chatScrollRect != null)
        {
            chatScrollRect.verticalNormalizedPosition = 0f;
        }
    }
}