using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.GroundTruth.LabelManagement;
using UnityEngine.Perception.Randomization.Randomizers;

/// <summary>
/// Randomizes a camera to simulate a humanoid robot's head-mounted camera
/// on a RoboCup soccer field. The camera is positioned at roughly head height,
/// and rotation is biased toward horizontal and downward-looking angles —
/// mimicking how a NAO/humanoid actually scans the field during a game.
///
/// Setup:
///   1. Add this Randomizer to your FixedLengthScenario via Add Randomizer.
///   2. Assign the cameraTransform to your scene Camera's Transform in the Inspector.
///      Leave null to auto-find Camera.main.
/// </summary>
[Serializable]
[AddRandomizerMenu("NomadZ/Humanoid Camera Randomizer")]

public class HumanoidCameraRandomizer : Randomizer
{
    // -------------------------------------------------------------------------
    // Robot position on field
    // -------------------------------------------------------------------------

    [Header("Robot Position on Field")]
    [Tooltip("Half-width of the RoboCup field (x-axis). Standard SPL field is 9m long, 6m wide.")]
    public float fieldWidth = 3.0f;

    [Tooltip("Half-length of the RoboCup field (z-axis).")]
    public float fieldHalfLength = 4.5f;

    [Tooltip("Camera height above ground. NAO upper camera is ~0.53m.")]
    public float cameraHeightMin = 0.50f;
    public float cameraHeightMax = 0.58f;

    // -------------------------------------------------------------------------
    // Pitch (up/down tilt)
    // NAO upper camera default: ~0 deg, lower camera: ~-38 deg
    // -------------------------------------------------------------------------

    [Header("Pitch (Vertical Tilt)")]
    [Tooltip("Range for the Gaussian mode. 0 = horizontal, negative = look down.")]
    public float pitchModeMin = -5f;
    public float pitchModeMax = -25f;

    [Tooltip("Hard clamp on pitch. Negative = downward.")]
    public float pitchMin = -60f;
    public float pitchMax = 15f;

    [Tooltip("Spread (sigma) of the Gaussian around the sampled pitch mode.")]
    public float pitchSigma = 10f;

    // -------------------------------------------------------------------------
    // Yaw (left/right pan)
    // -------------------------------------------------------------------------

    [Header("Yaw (Horizontal Pan)")]
    [Tooltip("Full yaw range in degrees. Robot mostly faces forward but scans sides.")]
    public float yawRange = 60f;  // ±30° from forward

    // -------------------------------------------------------------------------
    // Roll — small wobble only
    // -------------------------------------------------------------------------

    [Header("Roll")]
    [Tooltip("Sigma of roll in degrees. Simulates slight lean from walking phase.")]
    public float rollSigma = 3f;

    // -------------------------------------------------------------------------
    // Camera reference
    // -------------------------------------------------------------------------

    // -------------------------------------------------------------------------
    // Validity checks (all off by default = original behaviour)
    // -------------------------------------------------------------------------

    [Header("Validity Checks")]
    [Tooltip("Camera height is measured from the ground below the camera instead of world Y = 0.")]
    public bool heightAboveGround = false;
    [Tooltip("Objects that count as ground for heightAboveGround (highest hit wins).")]
    public List<string> groundObjects = new List<string> { "Terrain", "field" };

    [Tooltip("Reject positions outside x in [-fieldHalfLength, fieldHalfLength] and z in [0, fieldWidth].")]
    public bool stayOnField = false;

    [Tooltip("Minimum distance from the camera to any labeled object (robots, humans, balls, ...). 0 = off.")]
    public float minClearance = 0f;

    [Tooltip("Positions tried per iteration before giving up and keeping the last one.")]
    public int maxTries = 30;

    [Header("Camera Transform")]
    [Tooltip("Transform to randomize. Leave null to auto-find Camera.main.")]
    public Transform cameraTransform;

    // -------------------------------------------------------------------------
    // Randomizer lifecycle
    // -------------------------------------------------------------------------

    protected override void OnAwake()
    {
        if (cameraTransform == null)
        {
            var cam = Camera.main;
            if (cam != null)
                cameraTransform = cam.transform;
            else
                Debug.LogWarning("[HumanoidCameraRandomizer] No cameraTransform assigned and Camera.main not found.");
        }
    }

    protected override void OnIterationStart()
    {
        if (cameraTransform == null) return;

        CollectObstacles();
        bool valid = false;
        for (int attempt = 0; attempt < Mathf.Max(1, maxTries) && !valid; attempt++)
        {
            RandomizePosition();
            valid = IsValidPosition(cameraTransform.position);
        }
        if (!valid)
            Debug.LogWarning("[HumanoidCameraRandomizer] No valid camera position found, keeping the last one.");

        RandomizeRotation();
    }

    // -------------------------------------------------------------------------
    // Validity
    // -------------------------------------------------------------------------

    readonly List<Bounds> m_Obstacles = new List<Bounds>();

    void CollectObstacles()
    {
        m_Obstacles.Clear();
        if (minClearance <= 0f) return;

        foreach (var labeling in UnityEngine.Object.FindObjectsByType<Labeling>(FindObjectsSortMode.None))
        {
            var renderers = labeling.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) continue;
            var bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            m_Obstacles.Add(bounds);
        }
    }

    bool IsValidPosition(Vector3 position)
    {
        if (stayOnField && (Mathf.Abs(position.x) > fieldHalfLength || position.z < 0f || position.z > fieldWidth))
            return false;

        foreach (var bounds in m_Obstacles)
            if (bounds.SqrDistance(position) < minClearance * minClearance)
                return false;
        return true;
    }

    float GroundHeight(float x, float z)
    {
        var hits = Physics.RaycastAll(new Vector3(x, 100f, z), Vector3.down, 200f,
            Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
        float best = 0f;
        bool found = false;
        foreach (var hit in hits)
        {
            if (groundObjects.Contains(hit.collider.gameObject.name) && (!found || hit.point.y > best))
            {
                best = hit.point.y;
                found = true;
            }
        }
        return best;
    }

    // -------------------------------------------------------------------------
    // Position
    // -------------------------------------------------------------------------

    float Gaussian(float mean, float stdDev)
    {
        float u1 = 1.0f - UnityEngine.Random.value; // (0,1]
        float u2 = 1.0f - UnityEngine.Random.value;

        float randStdNormal = Mathf.Sqrt(-2.0f * Mathf.Log(u1)) *
                            Mathf.Sin(2.0f * Mathf.PI * u2);

        return mean + stdDev * randStdNormal;
    }
    private void RandomizePosition()
    {
        float z = Gaussian(fieldWidth / 2f, fieldWidth / 6f);
        float x = Gaussian(0f, fieldHalfLength / 3f);
        float y = UnityEngine.Random.Range(cameraHeightMin, cameraHeightMax);
        if (heightAboveGround)
            y += GroundHeight(x, z);
        cameraTransform.position = new Vector3(x, y, z);
    }

    // -------------------------------------------------------------------------
    // Rotation
    // -------------------------------------------------------------------------

    private void RandomizeRotation()
    {
        // Yaw: uniform within ±yawRange/2 from world forward (+Z)
        float yaw = UnityEngine.Random.Range(-yawRange * 0.5f, yawRange * 0.5f);

        // Pitch: pick a mode in [pitchModeMin, pitchModeMax], then draw from
        // a Gaussian around it — views cluster near horizontal/downward
        
        float pitch = UnityEngine.Random.Range(pitchModeMin, pitchModeMax);

        // Roll: small Gaussian wobble around 0
        float roll = SampleGaussianClamped(0f, rollSigma, -10f, 10f);

        cameraTransform.rotation = Quaternion.Euler(pitch, yaw, roll);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /// <summary>
    /// Samples a Gaussian N(mean, sigma) clamped to [min, max].
    /// </summary>
    private float SampleGaussianClamped(float mean, float sigma, float min, float max)
    {
        float sample = mean + sigma * BoxMullerSample();
        return Mathf.Clamp(sample, min, max);
    }

    /// <summary>
    /// Box-Muller transform — returns a standard normal N(0,1) sample.
    /// </summary>
    private float BoxMullerSample()
    {
        float u1 = 1f - UnityEngine.Random.value;  // avoid log(0)
        float u2 = 1f - UnityEngine.Random.value;
        return Mathf.Sqrt(-2f * Mathf.Log(u1)) * Mathf.Cos(2f * Mathf.PI * u2);
    }
}