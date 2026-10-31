import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

describe('EIIL Fusion Engine & Anomaly Rules', () => {
  // Calibration functions matching EIIL specifications
  function calculateFusionIntegrity(signals) {
    const weights = { sha256: 0.2, phash: 0.2, gps: 0.25, temporal: 0.15, vision: 0.2 };
    let score = 0;
    for (const key in weights) {
      if (signals[key]) {
        score += signals[key].score * weights[key];
      }
    }
    return Math.round(score);
  }

  function detectImpossibleTravel(locA, timeA, locB, timeB, maxKmh = 120) {
    const hours = Math.abs(new Date(timeB) - new Date(timeA)) / (1000 * 60 * 60);
    // Approximation for distance in km
    const latDiff = Math.abs(locA.lat - locB.lat) * 111;
    const lonDiff = Math.abs(locA.lon - locB.lon) * 111 * Math.cos(locA.lat * (Math.PI / 180));
    const distanceKm = Math.sqrt(latDiff * latDiff + lonDiff * lonDiff);
    if (hours === 0) return distanceKm > 0.5;
    const speed = distanceKm / hours;
    return speed > maxKmh;
  }

  test('calculateFusionIntegrity correctly weights multi-signal inputs', () => {
    const perfectSignals = {
      sha256: { score: 100 },
      phash: { score: 100 },
      gps: { score: 100 },
      temporal: { score: 100 },
      vision: { score: 100 }
    };
    assert.equal(calculateFusionIntegrity(perfectSignals), 100);

    const mixedSignals = {
      sha256: { score: 90 }, // 18
      phash: { score: 30 },  // 6
      gps: { score: 40 },    // 10
      temporal: { score: 50 },// 7.5
      vision: { score: 70 }  // 14
    };
    assert.equal(calculateFusionIntegrity(mixedSignals), 56);
  });

  test('detectImpossibleTravel flags implausible velocity between submissions', () => {
    // 500 km away in 15 minutes -> speed = 2000 km/h -> impossible!
    const locPune = { lat: 18.5204, lon: 73.8567 };
    const locSurat = { lat: 21.1702, lon: 72.8311 };
    const time1 = '2024-02-20T10:00:00Z';
    const time2 = '2024-02-20T10:15:00Z';

    const isImpossible = detectImpossibleTravel(locPune, time1, locSurat, time2, 120);
    assert.equal(isImpossible, true);
  });

  test('detectImpossibleTravel passes feasible velocity', () => {
    // 5 km away in 30 minutes -> speed = 10 km/h -> feasible
    const locA = { lat: 18.5204, lon: 73.8567 };
    const locB = { lat: 18.5500, lon: 73.8800 };
    const time1 = '2024-02-20T10:00:00Z';
    const time2 = '2024-02-20T10:30:00Z';

    const isImpossible = detectImpossibleTravel(locA, time1, locB, time2, 120);
    assert.equal(isImpossible, false);
  });
});
