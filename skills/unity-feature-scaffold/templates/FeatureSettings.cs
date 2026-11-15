using UnityEngine;

namespace MyGame.Feature
{
    /// <summary>Designer-facing tuning for the feature. One ScriptableObject per file, named after the class.</summary>
    [CreateAssetMenu(fileName = "FeatureSettings", menuName = "MyGame/Feature Settings")]
    public class FeatureSettings : ScriptableObject
    {
        private const string PulsePropertyName = "_Pulse";

        [field: SerializeField, Tooltip("Pulses per second.")]
        [field: Min(0f)]
        public float PulseSpeed { get; private set; } = 1f;

        /// <summary>Shader property id for the pulse amount, looked up once.</summary>
        public int PulsePropertyId { get; private set; }

        private void OnEnable()
        {
            PulsePropertyId = Shader.PropertyToID(PulsePropertyName);
        }
    }
}
