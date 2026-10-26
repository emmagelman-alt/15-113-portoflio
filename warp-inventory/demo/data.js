// Sample data for the Inventory demo. The catalog (part types, device categories, models and their
// typical parts lists) is copied from the starter catalog in
// code/supabase/migrations/20261023180100_inventory_starter_catalog.sql, trimmed to the devices used
// here. The processed counts and the parts cut are made up: the real numbers live in Andean's database.
window.INVENTORY_DEMO = {
  // Part types in catalog order. Top-level entries are groups in the part picker.
  componentTypes: [
    { code: "BOARDS", name: "Circuit boards" },
    { code: "MOTHERBOARD", name: "Motherboard / logic board", parent: "BOARDS" },
    { code: "DAUGHTERBOARD", name: "Other circuit board", parent: "BOARDS" },
    { code: "GPU", name: "Graphics card", parent: "BOARDS" },
    { code: "RAM", name: "Memory module", parent: "BOARDS" },
    { code: "CPU", name: "Processor", parent: "BOARDS" },
    { code: "STORAGE", name: "Storage" },
    { code: "HDD", name: "Hard drive", parent: "STORAGE" },
    { code: "SSD", name: "Solid-state drive", parent: "STORAGE" },
    { code: "OPTICAL-DRIVE", name: "Optical drive", parent: "STORAGE" },
    { code: "POWER", name: "Power" },
    { code: "PSU", name: "Power supply unit", parent: "POWER" },
    { code: "BATTERY-LI-ION", name: "Lithium-ion battery", parent: "POWER" },
    { code: "BATTERY-OTHER", name: "Other battery", parent: "POWER" },
    { code: "TRANSFORMER", name: "Transformer or coil", parent: "POWER" },
    { code: "MOVING-AUDIO", name: "Motors, fans and speakers" },
    { code: "FAN", name: "Fan", parent: "MOVING-AUDIO" },
    { code: "MOTOR", name: "Electric motor", parent: "MOVING-AUDIO" },
    { code: "SPEAKER", name: "Speaker", parent: "MOVING-AUDIO" },
    { code: "DISPLAY", name: "Display" },
    { code: "DISPLAY-PANEL", name: "Display panel", parent: "DISPLAY" },
    { code: "OTHER", name: "Other parts" },
    { code: "CAMERA-MODULE", name: "Camera module", parent: "OTHER" },
    { code: "HEATSINK", name: "Heat sink", parent: "OTHER" },
    { code: "CABLE", name: "Cables and wiring", parent: "OTHER" },
    { code: "CHASSIS", name: "Chassis and case panels", parent: "OTHER" }
  ],

  categories: [
    { code: "DESKTOP", name: "Desktop computer" },
    { code: "ALL-IN-ONE", name: "All-in-one computer" }
  ],

  models: [
    { code: "DELL-OPTIPLEX-SFF", category: "DESKTOP", manufacturer: "Dell", name: "OptiPlex (small form factor)" },
    { code: "DELL-OPTIPLEX-MT", category: "DESKTOP", manufacturer: "Dell", name: "OptiPlex (mini tower)" },
    { code: "HP-DESKTOP-TOWER", category: "DESKTOP", manufacturer: "HP", name: "Desktop tower (Compaq, ProDesk or EliteDesk)" }
  ],

  // Typical parts list per category, used when a device's model isn't known or has no list of its own
  categoryBom: {
    "DESKTOP": { MOTHERBOARD: 1, CPU: 1, RAM: 2, PSU: 1, HDD: 0.5, FAN: 1.5, HEATSINK: 1, "OPTICAL-DRIVE": 0.5, CHASSIS: 1 },
    "ALL-IN-ONE": { MOTHERBOARD: 1, CPU: 1, RAM: 2, PSU: 1, HDD: 1, "DISPLAY-PANEL": 1, FAN: 1, SPEAKER: 2, HEATSINK: 1, "CAMERA-MODULE": 1 }
  },

  // What the Lazarus run photos show inside each desktop model
  modelBom: {
    "DELL-OPTIPLEX-SFF": { MOTHERBOARD: 1, HEATSINK: 1, FAN: 1, PSU: 1, CHASSIS: 1, CPU: 1, RAM: 2, HDD: 0.5 },
    "DELL-OPTIPLEX-MT": { MOTHERBOARD: 1, HEATSINK: 1, PSU: 1, "OPTICAL-DRIVE": 1, CHASSIS: 1, FAN: 2, CPU: 1, RAM: 2, HDD: 0.3 },
    "HP-DESKTOP-TOWER": { MOTHERBOARD: 1, HEATSINK: 1, FAN: 1, PSU: 1, CHASSIS: 1, CPU: 1, RAM: 2, "OPTICAL-DRIVE": 0.5 }
  },

  // Sample: devices marked processed, by category and model (null = model not set)
  stock: [
    { category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", processed: 14 },
    { category: "DESKTOP", model: "DELL-OPTIPLEX-MT", processed: 11 },
    { category: "DESKTOP", model: "HP-DESKTOP-TOWER", processed: 7 },
    { category: "DESKTOP", model: null, processed: 6 },
    { category: "ALL-IN-ONE", model: null, processed: 3 }
  ],

  // Sample: parts already cut out. In Warp, Lazarus logs the case top face and the board for each
  // completed run, and people log the rest by hand. No category and no model = "any device".
  cut: [
    { type: "MOTHERBOARD", category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", qty: 14 },
    { type: "CHASSIS", category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", qty: 14 },
    { type: "FAN", category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", qty: 6 },
    { type: "PSU", category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", qty: 4 },
    { type: "RAM", category: "DESKTOP", model: "DELL-OPTIPLEX-SFF", qty: 10 },
    { type: "MOTHERBOARD", category: "DESKTOP", model: "DELL-OPTIPLEX-MT", qty: 11 },
    { type: "CHASSIS", category: "DESKTOP", model: "DELL-OPTIPLEX-MT", qty: 11 },
    { type: "OPTICAL-DRIVE", category: "DESKTOP", model: "DELL-OPTIPLEX-MT", qty: 5 },
    { type: "MOTHERBOARD", category: "DESKTOP", model: "HP-DESKTOP-TOWER", qty: 6 },
    { type: "CHASSIS", category: "DESKTOP", model: "HP-DESKTOP-TOWER", qty: 7 },
    { type: "MOTHERBOARD", category: "DESKTOP", model: null, qty: 5 },
    { type: "CHASSIS", category: "DESKTOP", model: null, qty: 6 },
    { type: "DISPLAY-PANEL", category: "ALL-IN-ONE", model: null, qty: 3 },
    { type: "SPEAKER", category: "ALL-IN-ONE", model: null, qty: 2 },
    { type: "HDD", category: null, model: null, qty: 4 }
  ]
};
