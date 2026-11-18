using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.GroundTruth.LabelManagement;
using UnityEngine.Perception.Randomization.Randomizers;
using UnityEngine.Perception.Randomization.Samplers;

/// <summary>
/// Controls how often and how big the ball appears in the picture. Each iteration it picks one case:
///   - no ball:  every ball is moved to a spot on the field outside the picture,
///   - near:     one ball is placed in the picture, nearDistance away from the camera,
///   - far:      one ball is placed in the picture, farDistance away from the camera.
/// The ball keeps clear of robots, humans and goals. Balls are the objects with a
/// FieldObjectRandomizerTag whose Labeling contains <see cref="ballLabel"/>.
/// Put it at the bottom of the list, below Humanoid Camera Randomizer, so the camera has its pose.
/// </summary>
[Serializable]
[AddRandomizerMenu("NomadZ/Ball In View Randomizer")]
public class BallInViewRandomizer : Randomizer
{
    [Header("Cases (shares are normalised, they don't have to add up to 1)")]
    public float noBallShare = 0.2f;
    public float nearShare = 0.4f;
    public float farShare = 0.4f;

    [Header("Distance from the camera (metres, along the ground)")]
    public Vector2 nearDistance = new Vector2(0.5f, 3f);
    public Vector2 farDistance = new Vector2(3f, 8f);

    [Header("Picture")]
    [Tooltip("Keep the ball centre this far inside the picture edges (fraction of the picture).")]
    [Range(0f, 0.3f)] public float edgeMargin = 0.03f;
    [Tooltip("Also move the other balls out of the picture, so at most one ball is visible.")]
    public bool otherBallsOutOfView = false;

    [Header("Area (world X/Z, metres), same as Field Object Randomizer")]
    public float xMin = -6f;
    public float xMax = 6f;
    public float zMin = 0f;
    public float zMax = 7f;

    [Header("Objects")]
    public string ballLabel = "ball";
    [Tooltip("Labels the ball must keep clear of.")]
    public List<string> obstacleLabels = new List<string> { "robot", "obstacle", "goal" };
    [Tooltip("Minimum gap between the ball and an obstacle (metres).")]
    public float margin = 0.05f;
    [Tooltip("Camera that takes the picture. Leave empty to use the main camera.")]
    public Camera targetCamera;

    const int k_MaxTries = 100;

    [NonSerialized] UniformSampler m_Random;
    [NonSerialized] readonly List<Bounds> m_Obstacles = new List<Bounds>();

    protected override void OnScenarioStart()
    {
        m_Random = new UniformSampler(0f, 1f);
        if (targetCamera == null)
            targetCamera = Camera.main;
        if (targetCamera == null)
            Debug.LogWarning("BallInViewRandomizer: no camera assigned and no main camera found.");
    }

    protected override void OnIterationStart()
    {
        if (targetCamera == null)
            return;

        var balls = new List<Transform>();
        foreach (var tag in tagManager.Query<FieldObjectRandomizerTag>())
        {
            var labeling = tag.GetComponentInChildren<Labeling>();
            if (labeling != null && labeling.labels.Contains(ballLabel))
                balls.Add(tag.transform);
        }
        if (balls.Count == 0)
            return;
        CollectObstacles();

        float total = noBallShare + nearShare + farShare;
        float pick = Rand() * total;
        Transform main = null;
        if (pick >= noBallShare)
        {
            main = balls[Mathf.Min((int)(Rand() * balls.Count), balls.Count - 1)];
            var range = pick < noBallShare + nearShare ? nearDistance : farDistance;
            if (!PlaceInView(main, range))
                Debug.LogWarning($"BallInViewRandomizer: no free spot in the picture for {main.name} " +
                                 $"at {range.x}-{range.y} m, left where it was.");
        }

        foreach (var ball in balls)
        {
            if (ball == main)
                continue;
            if (main == null || otherBallsOutOfView)
                PlaceOutOfView(ball);
        }
    }

    bool PlaceInView(Transform ball, Vector2 range)
    {
        var cam = targetCamera.transform;
        float yaw = Mathf.Atan2(cam.forward.x, cam.forward.z);
        float halfFov = Camera.VerticalToHorizontalFieldOfView(targetCamera.fieldOfView, targetCamera.aspect)
                        * 0.5f * Mathf.Deg2Rad;
        float radius = Radius(ball);

        for (int attempt = 0; attempt < k_MaxTries; attempt++)
        {
            float distance = Mathf.Lerp(range.x, range.y, Rand());
            float angle = yaw + (Rand() * 2f - 1f) * halfFov;
            var spot = new Vector2(cam.position.x + Mathf.Sin(angle) * distance,
                                   cam.position.z + Mathf.Cos(angle) * distance);
            if (!OnField(spot) || !IsClear(spot, radius))
                continue;
            MoveTo(ball, spot);
            if (InPicture(Centre(ball), edgeMargin))
                return true;
        }
        return false;
    }

    void PlaceOutOfView(Transform ball)
    {
        float radius = Radius(ball);
        for (int attempt = 0; attempt < k_MaxTries; attempt++)
        {
            var spot = new Vector2(Mathf.Lerp(xMin, xMax, Rand()), Mathf.Lerp(zMin, zMax, Rand()));
            if (!IsClear(spot, radius))
                continue;
            MoveTo(ball, spot);
            if (!Visible(ball))
                return;
        }
        Debug.LogWarning($"BallInViewRandomizer: no spot outside the picture found for {ball.name}.");
    }

    void MoveTo(Transform ball, Vector2 spot)
    {
        // Centre the visible ball on the spot; the height stays as the Field Object Randomizer left it.
        var centre = Centre(ball);
        ball.position += new Vector3(spot.x - centre.x, 0f, spot.y - centre.z);
    }

    bool OnField(Vector2 spot) => spot.x >= xMin && spot.x <= xMax && spot.y >= zMin && spot.y <= zMax;

    bool InPicture(Vector3 point, float inset)
    {
        var p = targetCamera.WorldToViewportPoint(point);
        return p.z > 0f && p.x > inset && p.x < 1f - inset && p.y > inset && p.y < 1f - inset;
    }

    bool Visible(Transform ball)
    {
        // Any part of the ball's box in the picture counts as visible.
        var b = Bounds(ball);
        var planes = GeometryUtility.CalculateFrustumPlanes(targetCamera);
        return GeometryUtility.TestPlanesAABB(planes, b);
    }

    void CollectObstacles()
    {
        m_Obstacles.Clear();
        foreach (var labeling in UnityEngine.Object.FindObjectsByType<Labeling>(FindObjectsSortMode.None))
        {
            bool obstacle = false;
            foreach (var label in labeling.labels)
                obstacle |= obstacleLabels.Contains(label);
            if (!obstacle)
                continue;
            var renderers = labeling.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                continue;
            var bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            m_Obstacles.Add(bounds);
        }
    }

    bool IsClear(Vector2 spot, float radius)
    {
        float gap = radius + margin;
        foreach (var b in m_Obstacles)
        {
            float dx = Mathf.Max(b.min.x - spot.x, 0f, spot.x - b.max.x);
            float dz = Mathf.Max(b.min.z - spot.y, 0f, spot.y - b.max.z);
            if (dx * dx + dz * dz < gap * gap)
                return false;
        }
        return true;
    }

    static Bounds Bounds(Transform ball)
    {
        var renderers = ball.GetComponentsInChildren<Renderer>();
        if (renderers.Length == 0)
            return new Bounds(ball.position, Vector3.zero);
        var bounds = renderers[0].bounds;
        foreach (var r in renderers)
            bounds.Encapsulate(r.bounds);
        return bounds;
    }

    static Vector3 Centre(Transform ball) => Bounds(ball).center;

    static float Radius(Transform ball)
    {
        var e = Bounds(ball).extents;
        return Mathf.Max(e.x, e.z);
    }

    float Rand() => m_Random.Sample();
}
