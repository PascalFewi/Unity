using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;
using UnityEngine.Perception.Randomization.Samplers;

/// <summary>
/// Places every robot with a RobotPlacementRandomizerTag each iteration: random pose variant of
/// its group, random yaw (always upright), random position, feet on the ground. Robots keep a gap
/// to each other and to everything the Field Object Randomizer placed (humans, balls), measured
/// from their actual footprints. Put it below Field Object Randomizer in the list.
/// </summary>
[Serializable]
[AddRandomizerMenu("NomadZ/Robot Placement Randomizer")]
public class RobotPlacementRandomizer : Randomizer
{
    [Header("Area (world X/Z, metres)")]
    public float xMin = -6f;
    public float xMax = 6f;
    public float zMin = 0f;
    public float zMax = 7f;

    [Header("Overlap check")]
    [Tooltip("Minimum gap between the footprints of two bodies (metres).")]
    public float margin = 0.1f;
    [Tooltip("Also keep clear of objects placed by the Field Object Randomizer (humans, balls).")]
    public bool avoidFieldObjects = true;

    [Header("Rotation")]
    [Range(0f, 360f)] public float yawRange = 360f;

    [Header("Ground")]
    [Tooltip("Objects the robots stand on; a ray from above picks the highest of them at each spot.")]
    public List<string> groundObjects = new List<string> { "Terrain", "field" };
    [Tooltip("Used when the ray hits none of the ground objects.")]
    public float fallbackGroundY = 0.54f;

    const int k_MaxTries = 50;

    class Pose
    {
        public Mesh mesh;
        public Material material;
        public Quaternion upright;   // mesh world rotation when standing with yaw 0
        public Vector3 worldScale;
    }

    [NonSerialized] Dictionary<string, List<Pose>> m_Groups;
    [NonSerialized] Dictionary<RobotPlacementRandomizerTag, Pose> m_OwnPose;
    [NonSerialized] List<Vector3> m_Placed;   // footprints: x, z = centre, y = radius
    [NonSerialized] UniformSampler m_Random;

    protected override void OnScenarioStart()
    {
        m_Groups = new Dictionary<string, List<Pose>>();
        m_OwnPose = new Dictionary<RobotPlacementRandomizerTag, Pose>();
        m_Placed = new List<Vector3>();
        m_Random = new UniformSampler(0f, 1f);

        // Collect each robot's pose as authored in the scene, grouped by type.
        foreach (var tag in tagManager.Query<RobotPlacementRandomizerTag>())
        {
            var filter = tag.MeshFilter;
            var renderer = filter != null ? filter.GetComponent<Renderer>() : null;
            if (renderer == null || filter.sharedMesh == null)
            {
                Debug.LogWarning($"RobotPlacementRandomizer: {tag.name} has no mesh, skipped.");
                continue;
            }

            var pose = new Pose
            {
                mesh = filter.sharedMesh,
                material = renderer.sharedMaterial,
                upright = UprightRotation(tag.transform, filter.transform),
                worldScale = filter.transform.lossyScale
            };
            m_OwnPose[tag] = pose;

            if (!m_Groups.TryGetValue(tag.Group, out var poses))
                m_Groups[tag.Group] = poses = new List<Pose>();
            if (!poses.Exists(p => p.mesh == pose.mesh && p.material == pose.material))
                poses.Add(pose);
        }
    }

    protected override void OnIterationStart()
    {
        if (m_OwnPose == null)
            return;

        m_Placed.Clear();
        if (avoidFieldObjects)
            AddFieldObjectFootprints();

        int overlapping = 0;
        foreach (var tag in tagManager.Query<RobotPlacementRandomizerTag>())
        {
            if (!m_OwnPose.TryGetValue(tag, out var pose))
                continue;
            if (tag.swapPose && m_Groups.TryGetValue(tag.Group, out var poses) && poses.Count > 1)
                pose = poses[Mathf.Min((int)(Rand() * poses.Count), poses.Count - 1)];

            float yaw = (Rand() - 0.5f) * yawRange;

            // Footprint radius of this pose and yaw (independent of where it stands).
            Place(tag, pose, yaw, Vector2.zero);
            var extents = tag.MeshFilter.GetComponent<Renderer>().bounds.extents;
            float radius = Mathf.Max(extents.x, extents.z);

            if (!PickSpot(radius, out var spot))
                overlapping++;
            Place(tag, pose, yaw, spot);
            m_Placed.Add(new Vector3(spot.x, radius, spot.y));
        }

        if (overlapping > 0)
            Debug.LogWarning($"RobotPlacementRandomizer: {overlapping} robot(s) found no free spot this iteration " +
                             "and overlap something. Fewer robots, a larger area or a smaller margin helps.");
    }

    void AddFieldObjectFootprints()
    {
        foreach (var tag in tagManager.Query<FieldObjectRandomizerTag>())
        {
            if (tag.GetComponent<RobotPlacementRandomizerTag>() != null)
                continue;
            var renderers = tag.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0)
                continue;
            var bounds = renderers[0].bounds;
            foreach (var r in renderers)
                bounds.Encapsulate(r.bounds);
            m_Placed.Add(new Vector3(bounds.center.x, Mathf.Max(bounds.extents.x, bounds.extents.z), bounds.center.z));
        }
    }

    void Place(RobotPlacementRandomizerTag tag, Pose pose, float yaw, Vector2 spot)
    {
        var root = tag.transform;
        var filter = tag.MeshFilter;
        var meshTransform = filter.transform;
        var renderer = filter.GetComponent<Renderer>();

        filter.sharedMesh = pose.mesh;
        renderer.sharedMaterial = pose.material;

        var yawRotation = Quaternion.Euler(0f, yaw, 0f);
        if (meshTransform == root)
        {
            root.rotation = yawRotation * pose.upright;
            SetWorldScale(root, pose.worldScale);
        }
        else
        {
            root.rotation = yawRotation;
            meshTransform.localPosition = Vector3.zero;
            meshTransform.rotation = yawRotation * pose.upright;
            SetWorldScale(meshTransform, pose.worldScale);
        }

        // Centre the visible body on the spot, then put its lowest point on the ground.
        root.position = new Vector3(spot.x, root.position.y, spot.y);
        var bounds = renderer.bounds;
        float groundY = GroundHeight(spot);
        root.position += new Vector3(spot.x - bounds.center.x, groundY - bounds.min.y, spot.y - bounds.center.z);
    }

    /// <summary>
    /// Random spot whose footprint keeps <see cref="margin"/> to all placed footprints. Returns false
    /// (and the spot with the most room) when none of k_MaxTries candidates is free.
    /// </summary>
    bool PickSpot(float radius, out Vector2 best)
    {
        best = Vector2.zero;
        float bestGap = float.NegativeInfinity;
        for (int attempt = 0; attempt < k_MaxTries; attempt++)
        {
            var spot = new Vector2(Mathf.Lerp(xMin, xMax, Rand()), Mathf.Lerp(zMin, zMax, Rand()));
            float gap = float.PositiveInfinity;
            foreach (var p in m_Placed)
                gap = Mathf.Min(gap, Vector2.Distance(spot, new Vector2(p.x, p.z)) - radius - p.y);
            if (gap > bestGap)
            {
                bestGap = gap;
                best = spot;
            }
            if (gap >= margin)
                return true;
        }
        return false;
    }

    float GroundHeight(Vector2 spot)
    {
        var hits = Physics.RaycastAll(new Vector3(spot.x, 100f, spot.y), Vector3.down, 200f,
            Physics.DefaultRaycastLayers, QueryTriggerInteraction.Ignore);
        float best = float.NegativeInfinity;
        foreach (var hit in hits)
            if (groundObjects.Contains(hit.collider.gameObject.name) && hit.point.y > best)
                best = hit.point.y;
        return float.IsNegativeInfinity(best) ? fallbackGroundY : best;
    }

    /// <summary>
    /// The mesh's world rotation when the robot stands upright with yaw 0: the authored rotation
    /// with its roll removed (as FieldObjectRandomizer did), then snapped exactly upright.
    /// </summary>
    static Quaternion UprightRotation(Transform root, Transform meshTransform)
    {
        var e = root.eulerAngles;
        var meshInRoot = Quaternion.Inverse(root.rotation) * meshTransform.rotation;
        var world = Quaternion.Euler(e.x, e.y, 0f) * meshInRoot;

        // Mesh-local axis that is closest to world up.
        var upLocal = Quaternion.Inverse(world) * Vector3.up;
        int axis = 0;
        for (int i = 1; i < 3; i++)
            if (Mathf.Abs(upLocal[i]) > Mathf.Abs(upLocal[axis]))
                axis = i;
        var snapped = Vector3.zero;
        snapped[axis] = Mathf.Sign(upLocal[axis]);

        world = Quaternion.FromToRotation(world * snapped, Vector3.up) * world;

        // Remove the yaw so all poses start facing the same way; the randomizer adds its own.
        var forward = Vector3.ProjectOnPlane(world * Vector3.forward, Vector3.up);
        if (forward.sqrMagnitude < 1e-6f)
            forward = Vector3.ProjectOnPlane(world * Vector3.right, Vector3.up);
        return Quaternion.Inverse(Quaternion.LookRotation(forward, Vector3.up)) * world;
    }

    static void SetWorldScale(Transform t, Vector3 worldScale)
    {
        var parent = t.parent != null ? t.parent.lossyScale : Vector3.one;
        t.localScale = new Vector3(worldScale.x / parent.x, worldScale.y / parent.y, worldScale.z / parent.z);
    }

    float Rand() => m_Random.Sample();
}
