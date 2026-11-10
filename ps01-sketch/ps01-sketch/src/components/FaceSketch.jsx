const DEFAULTS = { jaw: 50, eyeSize: 50, eyeSpacing: 50, noseWidth: 50, noseLength: 50, lips: 50, brow: 50, ageLines: 20 };
// Maps a 0-100 slider to a multiplier around 1 (50 = neutral).
const mult = (v, span) => 1 + ((v - 50) / 50) * span;

// Procedural pencil-style composite. Feature sliders reshape the geometry; disguises overlay on top.
export default function FaceSketch({ traits, disguises, svgRef }) {
  const f = { ...DEFAULTS, ...(traits.features || {}) };
  const { jaw, hairColor, face } = traits;
  const hair = disguises.has('Bald') ? 'bald' : disguises.has('Long Hair') ? 'long' : traits.hair;
  const ink = '#2a2a2e';

  const jawW = mult(f.jaw, 0.2);
  const eyeR = mult(f.eyeSize, 0.4);
  const eyeOff = ((f.eyeSpacing - 50) / 50) * 10;
  const lx = 120 - eyeOff, rx = 180 + eyeOff, ey = 152;
  const nw = 8 * mult(f.noseWidth, 0.35);
  const nt = 205 + ((f.noseLength - 50) / 50) * 12;
  const lip = 2 + (f.lips / 100) * 6;
  const dy = -((f.brow - 50) / 50) * 8;
  const headPath = jaw === 'sharp'
    ? 'M90 140 C90 70 210 70 210 140 L204 235 L172 292 L128 292 L96 235Z'
    : 'M90 140 C90 70 210 70 210 140 C210 215 190 285 150 300 C110 285 90 215 90 140Z';
  const jawT = `translate(150 0) scale(${jawW} 1) translate(-150 0)`;

  return (
    <svg ref={svgRef} viewBox="0 0 300 360" xmlns="http://www.w3.org/2000/svg" className="h-full w-full">
      <defs>
        <filter id="pencil"><feTurbulence baseFrequency="0.9" numOctaves="2" result="n" /><feDisplacementMap in="SourceGraphic" in2="n" scale="1.4" /></filter>
        <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><line x1="0" y1="0" x2="0" y2="5" stroke="#00000022" strokeWidth="1" /></pattern>
      </defs>
      <rect width="300" height="360" fill="#e9e4d6" />
      <rect width="300" height="360" fill="url(#hatch)" opacity=".5" />
      <g filter="url(#pencil)" stroke={ink} strokeWidth="2" strokeLinejoin="round" fill="none">
        {hair === 'long' && <path d="M80 150 C70 50 230 50 220 150 L230 310 L70 310Z" fill={hairColor} />}
        <g transform={`translate(150 0) scale(${face} 1) translate(-150 0)`}>
          <ellipse cx="88" cy="175" rx="8" ry="16" fill="#d9bfa3" />
          <ellipse cx="212" cy="175" rx="8" ry="16" fill="#d9bfa3" />
          <path d={headPath} fill="#e3c8aa" transform={jawT} />
          <path d={headPath} fill="url(#hatch)" stroke="none" transform={jawT} />
          {hair !== 'bald' && <path d="M88 140 C78 55 222 55 212 140 C205 105 190 92 150 92 C110 92 95 105 88 140Z" fill={hairColor} />}
          <path d={`M105 ${133 + dy} Q120 ${124 + dy} 137 ${131 + dy} M163 ${131 + dy} Q180 ${124 + dy} 195 ${133 + dy}`} strokeWidth="3" />
          <ellipse cx={lx} cy={ey} rx={11 * eyeR} ry={5 * eyeR} fill="#fff" />
          <circle cx={lx} cy={ey} r={3.2 * eyeR} fill={ink} />
          <ellipse cx={rx} cy={ey} rx={11 * eyeR} ry={5 * eyeR} fill="#fff" />
          <circle cx={rx} cy={ey} r={3.2 * eyeR} fill={ink} />
          <path d={`M150 160 L${150 - nw} ${nt} Q150 ${nt + 7} ${150 + nw} ${nt}`} />
          <path d={`M130 247 Q150 ${247 - lip} 170 247 M130 247 Q150 ${247 + lip + 4} 170 247`} />
          {f.ageLines > 0 && (
            <g opacity={f.ageLines / 100} strokeWidth="1.2">
              <path d="M112 108 Q150 103 188 108 M114 116 Q150 112 186 116" />
              <path d={`M${lx - 12} 170 Q${lx} 176 ${lx + 12} 170 M${rx - 12} 170 Q${rx} 176 ${rx + 12} 170`} />
              <path d="M128 214 Q121 230 125 242 M172 214 Q179 230 175 242" />
            </g>
          )}
          <g transform={jawT}>
            {disguises.has('Full Beard') && <path d="M92 200 C95 280 125 306 150 306 C175 306 205 280 208 200 C195 236 180 252 150 254 C120 252 105 236 92 200Z" fill={hairColor} opacity=".9" />}
          </g>
          {disguises.has('Mustache') && <path d="M122 238 Q150 224 178 238 Q150 247 122 238Z" fill={hairColor} />}
          {disguises.has('Wire-Rimmed Glasses') && (
            <g strokeWidth="1.8">
              <circle cx={lx} cy={ey} r="17" /><circle cx={rx} cy={ey} r="17" />
              <path d={`M${lx + 17} ${ey - 2} Q150 ${ey - 8} ${rx - 17} ${ey - 2}`} />
            </g>
          )}
          {disguises.has('Sunglasses') && (
            <g fill="#111" strokeWidth="2">
              <rect x={lx - 20} y={ey - 14} width="40" height="26" rx="9" />
              <rect x={rx - 20} y={ey - 14} width="40" height="26" rx="9" />
              <path d={`M${lx + 20} ${ey - 6} L${rx - 20} ${ey - 6}`} />
            </g>
          )}
          {disguises.has('Scar/Mark') && (
            <g stroke="#9c2f2f" strokeWidth="2.4">
              <path d="M170 118 L188 172" />
              <path d="M166 134 L176 131 M172 150 L183 147 M178 164 L188 161" strokeWidth="1.4" />
            </g>
          )}
        </g>
      </g>
      <text x="12" y="348" fontFamily="JetBrains Mono, monospace" fontSize="8" fill="#555">SUSPECT-A · COMPOSITE · #HACK26-451</text>
    </svg>
  );
}
