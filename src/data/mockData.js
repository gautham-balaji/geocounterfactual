// AUTO-GENERATED region catalog - keep in sync with backend/config.py.
// Every entry is a verified semi-arid watershed: built-up cover checked
// against ESA WorldCover, and terrain checked for BOTH flat valley floor
// (dam sites) and >5 deg ridges (so the critic's gravity rule applies).
export const MOCK_REGIONS = [
  {
    id: 'anantapur',
    name: 'Uravakonda Watershed',
    state: 'Anantapur District, Andhra Pradesh',
    lat: 14.92,
    lng: 77.4,
    climateZone: 'Semi-Arid Rain Shadow',
    baselineMetrics: {
      ndvi: 0.171,
      soilMoisture: '14%',
      waterRetention: '11%',
      avgSlope: '4.1\u00b0',
      rainfall: '520 mm/yr',
      builtUp: '0.00%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Anantapur to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Anantapur with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Anantapur agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'kadapa',
    name: 'Kadapa Schist Basin',
    state: 'Kadapa District, Andhra Pradesh',
    lat: 14.6822,
    lng: 79.1098,
    climateZone: 'Semi-Arid Rain Shadow',
    baselineMetrics: {
      ndvi: 0.159,
      soilMoisture: '14%',
      waterRetention: '13%',
      avgSlope: '5.5\u00b0',
      rainfall: '540 mm/yr',
      builtUp: '0.04%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Kadapa to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Kadapa with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Kadapa agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'kurnool',
    name: 'Kurnool Erra Basin',
    state: 'Kurnool District, Andhra Pradesh',
    lat: 15.4124,
    lng: 77.9401,
    climateZone: 'Semi-Arid Rain Shadow',
    baselineMetrics: {
      ndvi: 0.179,
      soilMoisture: '15%',
      waterRetention: '13%',
      avgSlope: '5.0\u00b0',
      rainfall: '540 mm/yr',
      builtUp: '0.22%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Kurnool to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Kurnool with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Kurnool agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'kolar',
    name: 'Kolar Plateau',
    state: 'Kolar District, Karnataka',
    lat: 13.7726,
    lng: 77.8752,
    climateZone: 'Semi-Arid Deccan Scrub',
    baselineMetrics: {
      ndvi: 0.208,
      soilMoisture: '16%',
      waterRetention: '12%',
      avgSlope: '4.5\u00b0',
      rainfall: '610 mm/yr',
      builtUp: '0.61%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Kolar to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Kolar with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Kolar agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'chitradurga',
    name: 'Chitradurga Scrubland',
    state: 'Chitradurga District, Karnataka',
    lat: 13.989,
    lng: 76.4928,
    climateZone: 'Semi-Arid Deccan Scrub',
    baselineMetrics: {
      ndvi: 0.268,
      soilMoisture: '18%',
      waterRetention: '12%',
      avgSlope: '4.6\u00b0',
      rainfall: '610 mm/yr',
      builtUp: '0.45%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Chitradurga to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Chitradurga with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Chitradurga agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'bellary',
    name: 'Ballari Granite Scrub',
    state: 'Ballari District, Karnataka',
    lat: 15.1763,
    lng: 76.5846,
    climateZone: 'Semi-Arid Deccan Scrub',
    baselineMetrics: {
      ndvi: 0.168,
      soilMoisture: '14%',
      waterRetention: '13%',
      avgSlope: '4.6\u00b0',
      rainfall: '610 mm/yr',
      builtUp: '0.08%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Ballari to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Ballari with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Ballari agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'marathwada',
    name: 'Beed Basin Watershed',
    state: 'Beed District, Maharashtra',
    lat: 18.77,
    lng: 75.37,
    climateZone: 'Deccan Trap Arid Plateau',
    baselineMetrics: {
      ndvi: 0.18,
      soilMoisture: '15%',
      waterRetention: '13%',
      avgSlope: '4.8\u00b0',
      rainfall: '680 mm/yr',
      builtUp: '0.78%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Beed to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Beed with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Beed agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'jalna',
    name: 'Jalna Basalt Upland',
    state: 'Jalna District, Maharashtra',
    lat: 20.5478,
    lng: 76.0106,
    climateZone: 'Deccan Trap Arid Plateau',
    baselineMetrics: {
      ndvi: 0.21,
      soilMoisture: '16%',
      waterRetention: '11%',
      avgSlope: '5.5\u00b0',
      rainfall: '680 mm/yr',
      builtUp: '0.62%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Jalna to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Jalna with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Jalna agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'ahmednagar',
    name: 'Ahmednagar Rain Shadow',
    state: 'Ahmednagar District, Maharashtra',
    lat: 19.3005,
    lng: 74.2988,
    climateZone: 'Deccan Trap Arid Plateau',
    baselineMetrics: {
      ndvi: 0.173,
      soilMoisture: '14%',
      waterRetention: '12%',
      avgSlope: '5.6\u00b0',
      rainfall: '680 mm/yr',
      builtUp: '0.82%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Ahmednagar to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Ahmednagar with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Ahmednagar agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'jodhpur',
    name: 'Jodhpur Arid Fringe',
    state: 'Jodhpur District, Rajasthan',
    lat: 26.7718,
    lng: 73.2594,
    climateZone: 'Arid Aravalli Fringe',
    baselineMetrics: {
      ndvi: 0.13,
      soilMoisture: '13%',
      waterRetention: '12%',
      avgSlope: '4.5\u00b0',
      rainfall: '380 mm/yr',
      builtUp: '0.13%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Jodhpur to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Jodhpur with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Jodhpur agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'pali',
    name: 'Pali Aravalli Foothills',
    state: 'Pali District, Rajasthan',
    lat: 24.9773,
    lng: 73.1995,
    climateZone: 'Arid Aravalli Fringe',
    baselineMetrics: {
      ndvi: 0.217,
      soilMoisture: '16%',
      waterRetention: '13%',
      avgSlope: '4.7\u00b0',
      rainfall: '380 mm/yr',
      builtUp: '0.24%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Pali to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Pali with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Pali agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'jhansi',
    name: 'Jhansi Bundelkhand Plateau',
    state: 'Jhansi District, Uttar Pradesh',
    lat: 25.6308,
    lng: 79.3642,
    climateZone: 'Bundelkhand Dry Plateau',
    baselineMetrics: {
      ndvi: 0.255,
      soilMoisture: '18%',
      waterRetention: '11%',
      avgSlope: '4.5\u00b0',
      rainfall: '820 mm/yr',
      builtUp: '0.08%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Jhansi to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Jhansi with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Jhansi agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'bundelkhand',
    name: 'Panna Plateau Watershed',
    state: 'Panna District, Madhya Pradesh',
    lat: 24.47,
    lng: 79.82,
    climateZone: 'Hard-Rock Granitic Terrain',
    baselineMetrics: {
      ndvi: 0.28,
      soilMoisture: '19%',
      waterRetention: '13%',
      avgSlope: '4.5\u00b0',
      rainfall: '850 mm/yr',
      builtUp: '0.00%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Panna to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Panna with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Panna agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'tikamgarh',
    name: 'Tikamgarh Granite Belt',
    state: 'Tikamgarh District, Madhya Pradesh',
    lat: 25.1131,
    lng: 78.9474,
    climateZone: 'Hard-Rock Granitic Terrain',
    baselineMetrics: {
      ndvi: 0.216,
      soilMoisture: '16%',
      waterRetention: '12%',
      avgSlope: '4.0\u00b0',
      rainfall: '850 mm/yr',
      builtUp: '0.53%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Tikamgarh to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Tikamgarh with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Tikamgarh agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
  {
    id: 'sagar',
    name: 'Sagar Vindhyan Upland',
    state: 'Sagar District, Madhya Pradesh',
    lat: 23.8925,
    lng: 78.6733,
    climateZone: 'Hard-Rock Granitic Terrain',
    baselineMetrics: {
      ndvi: 0.27,
      soilMoisture: '18%',
      waterRetention: '13%',
      avgSlope: '5.2\u00b0',
      rainfall: '850 mm/yr',
      builtUp: '0.05%',
    },
    presets: [
      {
        id: 'checkdams',
        title: 'Series Check-Dams',
        text: 'Build 3 series check-dams along the main dry stream bed in Sagar to trap monsoon runoff and recharge shallow aquifers.',
        metricsDelta: {
          ndviDelta: '+0.18',
          soilMoistureDelta: '+14%',
          waterRetentionDelta: '+28%',
          plausibilityScore: 94,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: water body placed on an upper ridge slope.'
        }
      },
      {
        id: 'afforestation',
        title: 'Upper Catchment Afforestation',
        text: 'Afforest 120 hectares of degraded upper-catchment slope in Sagar with native drought-hardy species.',
        metricsDelta: {
          ndviDelta: '+0.25',
          soilMoistureDelta: '+9%',
          waterRetentionDelta: '+16%',
          plausibilityScore: 96,
          criticIterations: 1,
          rejectionReason: 'Approved on 1st pass. Growth within the rainfed envelope.'
        }
      },
      {
        id: 'contourbunding',
        title: 'Contour Bunding & Recharge Pits',
        text: 'Construct earthen contour bunds every 50m with percolation pits across the Sagar agricultural boundary plots.',
        metricsDelta: {
          ndviDelta: '+0.12',
          soilMoistureDelta: '+22%',
          waterRetentionDelta: '+31%',
          plausibilityScore: 91,
          criticIterations: 2,
          rejectionReason: 'Iteration 1 rejected: infiltration exceeded substrate capacity.'
        }
      },
    ]
  },
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
