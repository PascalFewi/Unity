using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;

public enum JerseyAxis { Auto, X, Y, Z }

/// <summary>
/// Marks a robot that wears a jersey. The jersey recolours the robot's texture inside a band
/// of its mesh, given as fractions (0 = feet, 1 = head) along the mesh's up axis.
/// Select the robot in the editor to see the band as a yellow wire box.
/// </summary>
public class JerseyRandomizerTag : RandomizerTag
{
    [Tooltip("Mesh-local axis that points from feet to head. Auto picks the axis closest to world up at that " +
             "moment: right for every robot standing in Play mode, but the edit-mode gizmo is wrong for robots " +
             "that are tilted in the scene. Set it by hand only for robots that lie down.")]
    public JerseyAxis upAxis = JerseyAxis.Auto;

    [Tooltip("Head is at the negative end of the axis. Ignored when Up Axis is Auto.")]
    public bool invertAxis;

    [Header("Band (fraction of body height, 0 = feet, 1 = head)")]
    [Range(0f, 1f)] public float bandMin = 0.45f;
    [Range(0f, 1f)] public float bandMax = 0.75f;

    [Tooltip("Box size across the body relative to the mesh bounds; >1 so arms and edges are covered.")]
    public float sidePadding = 1.1f;

    [Tooltip("Recolour only white/light-grey parts inside the band (e.g. the K1's white torso plates). " +
             "Off = recolour everything inside the band.")]
    public bool whitePartsOnly = true;

    public MeshFilter MeshFilter => GetComponentInChildren<MeshFilter>();

    /// <summary>Band box in the local space of the robot's mesh transform.</summary>
    public bool TryGetBand(out Transform meshTransform, out Vector3 center, out Vector3 size) =>
        TryGetBand(out meshTransform, out center, out size, out _);

    /// <summary>Band box in mesh space, plus the index of the mesh axis the band runs along.</summary>
    public bool TryGetBand(out Transform meshTransform, out Vector3 center, out Vector3 size, out int axis)
    {
        axis = 1;
        var filter = MeshFilter;
        meshTransform = filter != null ? filter.transform : null;
        center = size = Vector3.zero;
        if (filter == null || filter.sharedMesh == null)
            return false;

        var bounds = filter.sharedMesh.bounds;
        ResolveAxis(meshTransform, out axis, out var headAtMax);

        float lo = bounds.min[axis], hi = bounds.max[axis];
        float a = Mathf.Min(bandMin, bandMax), b = Mathf.Max(bandMin, bandMax);
        float from = headAtMax ? Mathf.Lerp(lo, hi, a) : Mathf.Lerp(hi, lo, a);
        float to = headAtMax ? Mathf.Lerp(lo, hi, b) : Mathf.Lerp(hi, lo, b);

        center = bounds.center;
        size = bounds.size * sidePadding;
        center[axis] = (from + to) * 0.5f;
        size[axis] = Mathf.Abs(to - from);
        return true;
    }

    void ResolveAxis(Transform meshTransform, out int axis, out bool headAtMax)
    {
        if (upAxis != JerseyAxis.Auto)
        {
            axis = (int)upAxis - 1;
            headAtMax = !invertAxis;
            return;
        }

        var up = meshTransform.InverseTransformDirection(Vector3.up);
        axis = 0;
        for (int i = 1; i < 3; i++)
            if (Mathf.Abs(up[i]) > Mathf.Abs(up[axis]))
                axis = i;
        headAtMax = up[axis] > 0f;
    }

    void OnDrawGizmosSelected()
    {
        if (!TryGetBand(out var meshTransform, out var center, out var size))
            return;
        Gizmos.matrix = meshTransform.localToWorldMatrix;
        Gizmos.color = Color.yellow;
        Gizmos.DrawWireCube(center, size);
    }
}
