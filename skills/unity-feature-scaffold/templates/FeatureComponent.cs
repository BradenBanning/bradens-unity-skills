using UnityEngine;

namespace MyGame.Feature
{
    /// <summary>
    /// One MonoBehaviour per file, named after the class. All tuning comes from a settings asset so designers
    /// change it without touching code or scenes.
    /// </summary>
    public class FeatureComponent : MonoBehaviour
    {
        private static int _activeCount;

        [SerializeField, Tooltip("Tuning shared by every instance; create it with Create > MyGame > Feature Settings.")]
        private FeatureSettings _settings;

        [SerializeField, Tooltip("Renderer whose instanced material shows the effect.")]
        private Renderer _renderer;

        private Material _material;
        private float _elapsed;

        /// <summary>Number of enabled instances, reset each Play session.</summary>
        public static int ActiveCount => _activeCount;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        private static void ResetStatics()
        {
            _activeCount = 0;
        }

        private void Awake()
        {
            _material = _renderer.material;
        }

        private void OnEnable()
        {
            _activeCount++;
        }

        private void OnDisable()
        {
            _activeCount--;
        }

        private void Update()
        {
            _elapsed += Time.deltaTime;
            _material.SetFloat(_settings.PulsePropertyId, Mathf.PingPong(_elapsed * _settings.PulseSpeed, 1f));
        }

        private void OnDestroy()
        {
            Destroy(_material);
        }
    }
}
