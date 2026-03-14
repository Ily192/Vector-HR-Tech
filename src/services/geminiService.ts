import { GoogleGenAI } from "@google/genai";
import { Mood } from "../types";

// CORRECCIÓN: Usamos import.meta.env y el nombre correcto con prefijo VITE_
const apiKey = import.meta.env.VITE_API_KEY;

// Prevenimos que la app explote (pantalla blanca) si la key no carga
if (!apiKey) {
  console.error("⚠️ ERROR CRÍTICO: No se encontró la VITE_API_KEY. Revisa tu archivo .env o la configuración de Vercel.");
}

// Usamos un string vacío como fallback para que el constructor no lance el error "Uncaught Error" inmediatamente
const ai = new GoogleGenAI({ apiKey: apiKey || "" });

export const getEmotionalFeedback = async (mood: Mood, userName: string): Promise<string> => {
  // Si no hay API Key, retornamos un mensaje genérico sin intentar llamar a Google
  if (!apiKey) {
    return "¡Gracias por compartir! (Servicio de IA no disponible temporalmente)";
  }

  try {
    const prompt = `
      El usuario ${userName} ha registrado su estado de ánimo hoy como: "${mood}".
      Actúa como un coach empático de bienestar corporativo y "Salario Emocional".
      Genera un mensaje corto (máximo 2 frases) que sea motivador, comprensivo o que sugiera una pequeña pausa de bienestar.
      Si está feliz/emocionado, celebra con él. Si está estresado/cansado, ofrece apoyo.
      Responde en Español.
    `;

    const response = await ai.models.generateContent({
      model: 'gemini-2.5-flash', // OJO: Asegúrate que el modelo sea correcto (gemini-1.5-flash o gemini-2.0-flash-exp)
      contents: prompt,
    });

    // Ajuste seguro para obtener el texto dependiendo de la versión del SDK
    return response.text ? response.text() : "¡Gracias por compartir! Recuerda tomar descansos activos.";
    
  } catch (error) {
    console.error("Error fetching AI feedback:", error);
    return "Tu bienestar es importante para nosotros. ¡Que tengas un buen día!";
  }
};
