// Used by JerseyRandomizer, not for rendering in the scene.
// Pass 0: draws the robot mesh flat in UV space and writes 1 where the surface lies inside
//         the jersey band (a box in mesh space), 0 elsewhere -> a band mask in texture space.
// Pass 1: copies the robot texture and recolours the texels inside the (slightly dilated)
//         mask; optionally only the white-ish texels, keeping their shading.
Shader "Hidden/NomadZ/JerseyBake"
{
    Properties
    {
        _MainTex ("Texture", 2D) = "white" {}
        _MaskTex ("Mask", 2D) = "black" {}
    }

    SubShader
    {
        Cull Off ZWrite Off ZTest Always

        Pass
        {
            BlendOp Max
            Blend One One

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0

            float3 _BandCenter;
            float3 _BandSize;
            float _BandSoftness;

            struct appdata { float4 vertex : POSITION; float2 uv : TEXCOORD0; };
            struct v2f { float4 pos : SV_POSITION; float3 objPos : TEXCOORD0; };

            v2f vert(appdata v)
            {
                v2f o;
                float2 p = v.uv * 2.0 - 1.0;
                #if UNITY_UV_STARTS_AT_TOP
                p.y = -p.y;
                #endif
                o.pos = float4(p, 0.5, 1.0);
                o.objPos = v.vertex.xyz;
                return o;
            }

            float4 frag(v2f i) : SV_Target
            {
                // Signed distance to the box surface (< 0 inside).
                float3 d = abs(i.objPos - _BandCenter) - _BandSize * 0.5;
                float outside = max(d.x, max(d.y, d.z));
                float w = 1.0 - smoothstep(-_BandSoftness, _BandSoftness, outside);
                return float4(w, w, w, 1.0);
            }
            ENDCG
        }

        Pass
        {
            CGPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #pragma target 3.0
            #include "UnityCG.cginc"

            sampler2D _MainTex;
            sampler2D _MaskTex;
            float4 _MaskTex_TexelSize;
            float4 _JerseyColor;    // linear
            float _Opacity;
            float _WhiteOnly;
            float _WhiteSatMax;     // sRGB saturation below this counts as white/grey
            float _WhiteValMin;     // sRGB brightness above this counts as white
            float _ShadeRef;        // brightness that maps to the full jersey colour
            float _DilatePx;

            float4 frag(v2f_img i) : SV_Target
            {
                float4 c = tex2D(_MainTex, i.uv);

                // Dilate the mask a little so texels at UV island borders are recoloured too.
                float m = 0.0;
                for (int x = -1; x <= 1; x++)
                    for (int y = -1; y <= 1; y++)
                        m = max(m, tex2D(_MaskTex, i.uv + float2(x, y) * _MaskTex_TexelSize.xy * _DilatePx).r);

                float3 s = LinearToGammaSpace(c.rgb);
                float mx = max(s.r, max(s.g, s.b));
                float mn = min(s.r, min(s.g, s.b));
                float sat = mx > 1e-4 ? (mx - mn) / mx : 0.0;
                float lum = dot(s, float3(0.299, 0.587, 0.114));

                float white = (1.0 - smoothstep(_WhiteSatMax * 0.7, _WhiteSatMax, sat))
                            * smoothstep(_WhiteValMin * 0.8, _WhiteValMin, mx);
                float key = _WhiteOnly > 0.5 ? white : 1.0;

                // Keep the shading of the original surface.
                float shade = _WhiteOnly > 0.5 ? saturate(lum / _ShadeRef) : saturate(0.35 + lum);
                float3 tinted = _JerseyColor.rgb * GammaToLinearSpace(shade.xxx);

                return float4(lerp(c.rgb, tinted, saturate(m * key * _Opacity)), c.a);
            }
            ENDCG
        }
    }
}
