using UnityEngine;

namespace MyGame.Rendering
{
    /// <summary>
    /// Per-object material effect through an instanced material. Renderer.material clones the shared material once,
    /// so the object keeps SRP Batcher compatibility (MaterialPropertyBlocks would break it). The clone is destroyed
    /// with the component so it doesn't leak.
    /// </summary>
    public class InstancedMaterialEffect : MonoBehaviour
    {
        private const string EmissionColorName = "_EmissionColor";
        private const string EmissionKeyword = "_EMISSION";

        private static readonly int EmissionColorId = Shader.PropertyToID(EmissionColorName);

        [SerializeField, Tooltip("Renderer using the UberLit material.")]
        private Renderer _renderer;

        [SerializeField, Tooltip("HDR emission color applied while the effect is on.")]
        [ColorUsage(false, true)]
        private Color _highlightColor = Color.white;

        private Material _material;

        /// <summary>Turns the highlight on or off for this object only.</summary>
        public void SetHighlighted(bool highlighted)
        {
            if (_material == null)
            {
                _material = _renderer.material;
            }

            if (highlighted)
            {
                _material.EnableKeyword(EmissionKeyword);
                _material.SetColor(EmissionColorId, _highlightColor);
            }
            else
            {
                _material.DisableKeyword(EmissionKeyword);
            }
        }

        private void OnDestroy()
        {
            if (_material != null)
            {
                Destroy(_material);
            }
        }
    }
}
