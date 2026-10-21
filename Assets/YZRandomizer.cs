using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Perception.Randomization.Randomizers;



[Serializable]
[AddRandomizerMenu("NomadZ/Y Z Randomizer")]
public class YZRandomizer : Randomizer
{
    [Header("X Offset Range")]
    public float minOffsety = -0.1f;
    public float maxOffsety = 0.1f;

    public float minOffsetz = -0.1f;
    public float maxOffsetz = 0.1f;


    // Each object's position before the first offset. Offsets are applied to this,
    // not to the current position, so they don't accumulate into a random walk.
    Dictionary<Transform, Vector3> originalPositions;

    protected override void OnScenarioStart()
    {
        originalPositions = new Dictionary<Transform, Vector3>();
    }

    protected override void OnIterationStart()
    {
        var tags = tagManager.Query<YZRandomizerTag>();

        foreach (var tag in tags)
        {
            var obj = tag.transform;

            // Store original position safely per object
            if (!originalPositions.TryGetValue(obj, out Vector3 basePos))
            {
                basePos = obj.position;
                originalPositions[obj] = basePos;
            }

            float offsety = UnityEngine.Random.Range(minOffsety, maxOffsety);
            float offsetz = UnityEngine.Random.Range(minOffsetz, maxOffsetz);

            obj.position = new Vector3(
                basePos.x,
                basePos.y + offsety,
                basePos.z + offsetz
            );
        }
    }
}
