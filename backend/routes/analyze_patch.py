from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from routes.analyze import analyze_paper, list_analyses, get_analysis, logger, t
