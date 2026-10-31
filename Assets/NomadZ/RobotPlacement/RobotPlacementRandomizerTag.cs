using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;

/// <summary>
/// Marks a robot that RobotPlacementRandomizer places on the field every iteration.
/// Robots with the same group swap between each other's poses (mesh + material).
/// </summary>
public class RobotPlacementRandomizerTag : RandomizerTag
{
    [Tooltip("Pose group. Empty = the object name before ' (', e.g. 'K1 (3)' -> 'K1'.")]
    public string group = "";

    [Tooltip("Randomly switch to another pose of the same group each iteration.")]
    public bool swapPose = true;

    public string Group
    {
        get
        {
            if (!string.IsNullOrEmpty(group))
                return group;
            int cut = name.IndexOf(" (");
            return cut > 0 ? name.Substring(0, cut) : name;
        }
    }

    public MeshFilter MeshFilter => GetComponentInChildren<MeshFilter>();
}
