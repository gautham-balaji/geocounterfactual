export const MOCK_REGIONS = [
  {
    id: 'anantapur',
    name: 'Anantapur Watershed Zone',
    state: 'Andhra Pradesh, India',
    lat: 14.6819,
    lng: 77.6006,
    climateZone: 'Semi-Arid Rain Shadow',
    baselineMetrics: {
      ndvi: 0.22,
      soilMoisture: '18%',
      waterRetention: '12%',
      avgSlope: '4.2°',
      rainfall: '520 mm/yr'
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Central Stream Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: Water body initially placed on 14° upper ridge slope without drainage basin.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Ridge Afforestation',
        text: 'Afforest 150 hectares of degraded upper-catchment slope with native Acacia & Neem broadleaf canopy to prevent topsoil erosion.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+19%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Biomass growth rate compliant with 5-year precipitation caps.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Percolation Pits',
        text: 'Construct earthen contour bunds every 50m with recharge pits across agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 3,
          rejectionReason: 'Iteration 1 & 2 rejected: Soil porosity exceeded infiltration capacity for clay-loam substrate.'
        }
      }
    ]
  },
  {
    id: 'marathwada',
    name: 'Marathwada Drought Basin',
    state: 'Maharashtra, India',
    lat: 19.8762,
    lng: 75.3433,
    climateZone: 'Deccan Trap Arid Plateau',
    baselineMetrics: {
      ndvi: 0.18,
      soilMoisture: '14%',
      waterRetention: '8%',
      avgSlope: '3.5°',
      rainfall: '680 mm/yr'
    },
    presets: [
      {
        id: 'farmponds',
        title: 'Distributed Farm Ponds Network',
        text: 'Excavate 12 plastic-lined farm ponds along natural contour dips to harvest surface runoff.',
        metricsDelta: {
          ndviDelta: '+0.16',
          soilMoistureDelta: '+18%',
          waterRetentionDelta: '+34%',
          plausibilityScore: 93,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: Surface evaporation rate uncompensated in peak summer thermal band.'
        }
      }
    ]
  },
  {
    id: 'bundelkhand',
    name: 'Bundelkhand Semi-Arid Basin',
    state: 'Madhya Pradesh, India',
    lat: 24.8986,
    lng: 79.5937,
    climateZone: 'Hard-Rock Granitic Terrain',
    baselineMetrics: {
      ndvi: 0.28,
      soilMoisture: '21%',
      waterRetention: '15%',
      avgSlope: '6.1°',
      rainfall: '850 mm/yr'
    },
    presets: [
      {
        id: 'stopdams',
        title: 'Granitic Stream Stop-Dams',
        text: 'Construct 2 masonry stop-dams with boulder rip-rap across rocky stream channels.',
        metricsDelta: {
          ndviDelta: '+0.21',
          soilMoistureDelta: '+16%',
          waterRetentionDelta: '+25%',
          plausibilityScore: 95,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Bedrock impermeability verified against DEM.'
        }
      }
    ]
  }
];

export const MOCK_AGENT_NODES = [
  {
    id: 'node-1',
    name: 'Input Handler',
    shortCode: 'N1',
    role: 'Multi-Modal Signal Parsing',
    description: 'Ingests Sentinel-2 GeoTIFF 10m bands & parses natural language intervention text into canonical spatial intent vectors.',
    status: 'idle',
    icon: 'FileText'
  },
  {
    id: 'node-2',
    name: 'Intervention-Planner',
    shortCode: 'N2',
    role: 'Spatial Constraint Masker',
    description: 'Generates spatial change masks, locates stream channels, and paints pixel candidate zones for intervention placement.',
    status: 'idle',
    icon: 'MapPin'
  },
  {
    id: 'node-3',
    name: 'Eco-Hydrological Dynamics',
    shortCode: 'N3',
    role: 'Physics & Biome Engine',
    description: 'Models multi-year vegetation biomass expansion (NDVI growth curves) and groundwater infiltration dynamics.',
    status: 'idle',
    icon: 'Trees'
  },
  {
    id: 'node-4',
    name: 'Generator (Diffusion Model)',
    shortCode: 'N4',
    role: 'Latent Image Synthesizer',
    description: 'Conditioned latent diffusion engine (ControlNet + SD backbone) synthesizing high-resolution future satellite imagery.',
    status: 'idle',
    icon: 'Cpu'
  },
  {
    id: 'node-5',
    name: 'Physical-Plausibility Critic',
    shortCode: 'N5',
    role: 'Physics Violation Gatekeeper',
    description: 'Inspects generated scene against DEM slopes, spectral reflectance limits, and water-body gravimetric constraints.',
    status: 'idle',
    icon: 'ShieldCheck'
  }
];

export const MOCK_CRITIC_CHATTER = [
  { step: 1, agent: 'Input Handler', type: 'info', text: 'Received query: "Build 3 check-dams along central dry stream bed" for Anantapur region.' },
  { step: 2, agent: 'Input Handler', type: 'info', text: 'Fetched Sentinel-2 bands (B2, B3, B4, B8, B11, B12). Resolution: 10m/px.' },
  { step: 3, agent: 'Intervention-Planner', type: 'info', text: 'Extracted drainage network using Copernicus DEM 30m flow accumulation map.' },
  { step: 4, agent: 'Intervention-Planner', type: 'success', text: 'Target stream segment identified: 1.4km length, 3 candidate barrier coordinates.' },
  { step: 5, agent: 'Eco-Hydrological Dynamics', type: 'info', text: 'Simulating 5-year post-intervention hydrology: Expected moisture plume expansion = +14% radius.' },
  { step: 6, agent: 'Generator (Diffusion)', type: 'info', text: 'Synthesizing candidate image frame #1 via ControlNet conditioning map...' },
  { step: 7, agent: 'Physical-Plausibility Critic', type: 'warning', text: 'CRITIC ALERT: Water body detected on 14.2° elevation slope! Surface water cannot remain stationary on steep gradients.' },
  { step: 8, agent: 'Physical-Plausibility Critic', type: 'reject', text: 'REJECTED Iteration #1 (Violation Score: 0.62). Sending feedback matrix back to Generator.' },
  { step: 9, agent: 'Generator (Diffusion)', type: 'info', text: 'Feedback loop engaged! Adjusting depth map mask & masking out illegal slope coordinates.' },
  { step: 10, agent: 'Generator (Diffusion)', type: 'info', text: 'Re-synthesizing candidate image frame #2 with corrected terrain elevation boundary...' },
  { step: 11, agent: 'Physical-Plausibility Critic', type: 'info', text: 'Re-evaluating Frame #2: Water bodies mapped inside stream channel bed. Slope: 1.8°. NDVI transition: physically continuous.' },
  { step: 12, agent: 'Physical-Plausibility Critic', type: 'success', text: 'PASSED Physical Plausibility Check (Plausibility Score: 94%). Output approved!' }
];

export const MOCK_METHODOLOGY_CARDS = [
  {
    id: 'sentinel2',
    title: 'Sentinel-2 10m Optical Imagery',
    category: 'Remote Sensing Substrate',
    icon: 'Layers',
    badge: '10m Resolution',
    description: 'Ingests 13 spectral bands from ESA Sentinel-2 MSI satellite. Crucial bands include Band 4 (Red), Band 8 (NIR), and Band 11 (SWIR-1) for biomass and soil moisture evaluation.',
    specs: [
      'Revisit Time: 5 days',
      'Spatial Resolution: 10m - 20m',
      'Spectral Coverage: VNIR + SWIR',
      'Radiometric Resolution: 12-bit'
    ]
  },
  {
    id: 'gee',
    title: 'Google Earth Engine Pipeline',
    category: 'Data Preprocessing',
    icon: 'Database',
    badge: 'Cloud Processing',
    description: 'Automated GEE cloud scripts filter atmospheric cloud cover (<5%), apply Terrain Illumination Correction, and co-register historical multi-temporal image stacks.',
    specs: [
      'Top-of-Atmosphere (TOA) Reflectance',
      'Copernicus 30m Global DEM',
      'S2 Surface Reflectance (Harmonized)',
      'Sub-pixel Spatial Alignment'
    ]
  },
  {
    id: 'ndvi_moisture',
    title: 'NDVI & Soil Moisture Physics Constraints',
    category: 'Domain Science Rules',
    icon: 'Activity',
    badge: 'Spectral Index Rules',
    description: 'Employs Normalized Difference Vegetation Index (NDVI) and Land Surface Water Index (LSWI) constraints to bound physical changes within natural biological growth speeds.',
    specs: [
      'NDVI Formula: (B8 - B4) / (B8 + B4)',
      'NDWI Formula: (B3 - B8) / (B3 + B8)',
      'Max NDVI delta cap: +0.35 / year',
      'Spectral signature continuity check'
    ]
  },
  {
    id: 'controlnet',
    title: 'ControlNet Spatial Conditioning',
    category: 'Generative Architecture',
    icon: 'Cpu',
    badge: 'Diffusion Backbone',
    description: 'Uses a fine-tuned Stable Diffusion backbone with ControlNet edge & elevation conditioning channels. Ensures original terrain structures remain untouched while editing intervention zones.',
    specs: [
      'Latent Diffusion Model (LDM)',
      'ControlNet Depth & Canny Guidance',
      'Cross-Attention Condition Vectors',
      'Zero-shot spatial preservation'
    ]
  },
  {
    id: 'agentic_loop',
    title: 'LangGraph Multi-Agent Critic Loop',
    category: 'System Orchestration',
    icon: 'GitCompare',
    badge: 'Novel Contribution',
    description: 'Cyclic graph orchestration implemented in LangGraph. The Physical-Plausibility Critic evaluates candidate scenes and triggers automated regeneration feedback loops when rules are violated.',
    specs: [
      'Cyclic Graph State Machine',
      'Feedback tensor mask transmission',
      'Quantitative violation score calculation',
      'Proven 42% reduction in generative hallucinations'
    ]
  }
];
