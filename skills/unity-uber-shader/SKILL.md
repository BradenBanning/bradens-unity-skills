---
name: unity-uber-shader
description: Create and extend a URP project's single SRP Batcher compatible opaque shader (UberLit) instead of writing new shaders - add a property, its UnityPerMaterial CBUFFER entry and a shader_feature_local keyword in every pass - and drive per-object looks with instanced materials, never MaterialPropertyBlocks. Use when an opaque surface needs a new look (emission pulse, dissolve, tint, triplanar, rim, wind), when someone is about to write a new .shader or Lit variant, when materials break SRP batching, or when creating the project's first UberLit.
---

# One uber shader for every opaque surface

Every opaque material uses one shader, `UberLit`. One shader with features toggled by local keywords keeps the
SRP Batcher batching everything, keeps variants under control, and gives artists one material inspector to learn.
Transparent effects use Shader Graph and particles use VFX Graph, so this shader stays opaque.

The plugin's hooks warn when a new `.shader` file other than UberLit is written, and block MaterialPropertyBlock.

## Create it (first time)

1. Copy `templates/UberLit.shader` to `Assets/_Project/Rendering/Shaders/UberLit.shader` (scaffold the Rendering
   feature first with the unity-feature-scaffold skill if it doesn't exist).
2. Refresh the Editor and read the Console: the shader must compile with no errors or warnings in every pass. Check
   the Frame Debugger or the material inspector's "SRP Batcher: compatible" line.
3. Create `M_<Name>` materials from it and swap opaque URP Lit materials over as they're touched.

The template has ForwardLit (PBR with main and additional lights, soft shadows, SSAO, light layers, Forward+
clustered lights, cookies, fog), ShadowCaster, DepthOnly and DepthNormals, plus `_NORMALMAP` and `_EMISSION`
features. It reuses URP's own ShadowCaster, DepthOnly and DepthNormals pass files, which read `_BaseMap`,
`_BaseColor` and `_Cutoff` from the CBUFFER. It leaves out lightmaps, the GBuffer (deferred) pass and Meta; add them
as features when the project needs them (copy the keywords and pass from URP's `Shaders/Lit.shader` in
`Library/PackageCache/com.unity.render-pipelines.universal@*` for the installed version).

## Add a feature

Each feature follows the same four steps; keep the order so the SRP Batcher stays compatible.

1. **Property** in `Properties`, with a `[Toggle(_FEATURE)]` float for the switch:
   `[Toggle(_DISSOLVE)] _UseDissolve("Dissolve", Float) = 0` and `_DissolveAmount("Dissolve Amount", Range(0,1)) = 0`.
2. **CBUFFER**: add every new non-texture property to `CBUFFER_START(UnityPerMaterial)` in the shared
   `HLSLINCLUDE` block. Every pass must see the same CBUFFER layout, or the SRP Batcher drops the shader. Textures go
   outside the CBUFFER (`TEXTURE2D(_NoiseMap); SAMPLER(sampler_NoiseMap);`), with their `_ST` inside it if tiled.
3. **Keyword in each pass** the feature affects: `#pragma shader_feature_local _DISSOLVE` (or
   `shader_feature_local_fragment` when only the fragment stage changes). A feature that changes the silhouette
   (dissolve, alpha clip, vertex wind) must be added to ShadowCaster, DepthOnly and DepthNormals too, or shadows and
   depth won't match the visible surface.
4. **Code** inside `#if defined(_DISSOLVE)` blocks, so materials without the feature pay nothing.

Never `multi_compile` a material feature (it builds every variant for every material); `shader_feature_local` strips
unused ones. Keep the keyword count per pass low: about 64 local keywords is the hard limit.

## Per-object effects

Per-object values (a highlight on the selected unit, a hit flash) use an instanced material:
`renderer.material` clones the shared material once for that renderer, and the component destroys the clone in
`OnDestroy` (see `templates/InstancedMaterialEffect.cs`). Never use `MaterialPropertyBlock` (it breaks SRP batching;
the edit hook blocks it). Cache property ids with `Shader.PropertyToID` in a static readonly field, and turn features
on with `material.EnableKeyword`.

## Verify

- The Console shows no shader errors after a refresh, on every platform target the project builds for.
- The material inspector shows SRP Batcher compatible; the Frame Debugger shows the objects in SRP Batch draws.
- Shadows, SSAO and depth-based effects match the surface with each new feature on and off.
- Say which of these were checked by hand; none of them can be tested from a PlayMode test.
