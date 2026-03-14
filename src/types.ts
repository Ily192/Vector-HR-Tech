export enum Role {
  ADMIN = 'Admin',
  RH = 'RH',
  COLLABORATOR = 'Colaborador',
  CEO_RH = 'Ceo RH',
  CEO_CLIENTE = 'Ceo Cliente'
}

export enum RequestStatus {
  PENDING = 'Pendiente',
  IN_PROGRESS = 'En Proceso',
  COMPLETED = 'Completado'
}

export enum RequestType {
  CERTIFICATE = 'Constancia',
  REFERENCE = 'Referencia',
  CONSULTA = 'Consulta'
}

export interface Empresa {
  id: string;
  nombre: string;
  nitIdentificacion?: string;
  logoUrl?: string;
}

export interface User {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  empresaId?: string;
  
  // Campos de Perfil extendidos
  area?: string;
  rolPuesto?: string;
  fechaIngreso?: string;
  tipoIdentificacion?: string;
  numeroIdentificacion?: string;
  correoPersonal?: string;
  telefonoWhatsapp?: string;
  
  avatarUrl?: string;
}

export interface Solicitud {
  id: string;
  colaboradorId: string;
  empresaId: string;
  tipo: RequestType;
  estatus: RequestStatus;
  detalles?: string;
  archivoUrl?: string; // URL del PDF generado por n8n
  createdAt: string;
}

export interface ChatMessage {
  id: string;
  emisorId: string;
  receptorId?: string;
  mensaje: string;
  googleThreadId?: string;
  createdAt: string;
}

// Añade esto al final de src/types.ts

export enum Mood {
  HAPPY = 'Happy',
  NEUTRAL = 'Neutral',
  STRESSED = 'Stressed',
  TIRED = 'Tired',
  EXCITED = 'Excited'
}

export interface Project {
  id: string;
  name: string;
  role: string;
  status: 'Active' | 'Completed' | 'On Hold';
}

export interface EmotionalLog {
  date: string;
  mood: Mood;
  aiFeedback?: string;
}
